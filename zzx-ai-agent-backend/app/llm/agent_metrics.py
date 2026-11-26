"""Runtime metrics for the LangChain ReAct engine.

The MultiStepAgent engines track model calls, tool calls and token usage inside
their own loops. LangChain hides those details, so a callback handler collects
them from the framework's lifecycle events instead. This keeps the [META]
payload comparable across all three engines.
"""
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from app.agent_core.observability import AgentTrace


def _extract_token_usage(response: Any) -> tuple[int, int]:
    """Read token usage from either llm_output or message.usage_metadata."""
    llm_output = getattr(response, "llm_output", None) or {}
    if isinstance(llm_output, dict):
        usage = llm_output.get("token_usage") or llm_output.get("usage")
        if isinstance(usage, dict):
            prompt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            completion = usage.get("completion_tokens") or usage.get("output_tokens") or 0
            if prompt or completion:
                return int(prompt), int(completion)

    prompt = completion = 0
    for generation in getattr(response, "generations", None) or []:
        for item in generation:
            message = getattr(item, "message", None)
            metadata = getattr(message, "usage_metadata", None)
            if isinstance(metadata, dict):
                prompt += int(metadata.get("input_tokens") or 0)
                completion += int(metadata.get("output_tokens") or 0)
    return prompt, completion


class AgentMetricsCallback(BaseCallbackHandler):
    """Collect one agent run's LLM calls, tool calls and token usage."""

    def __init__(self, trace: AgentTrace | None = None):
        self.trace = trace
        self.llm_calls = 0
        self.tool_calls = 0
        self.tool_errors = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        # Nested tool calls (for example get_now_weather -> MCP get_weather)
        # also emit tool callbacks. Track top-level tool run ids so the public
        # "tool_calls" metric counts user-facing tools, not internal hops.
        self._active_tools: set[str] = set()

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        self.llm_calls += 1
        prompt, completion = _extract_token_usage(response)
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        if self.trace:
            self.trace.llm_end(
                call=self.llm_calls,
                prompt_tokens=prompt,
                completion_tokens=completion,
                cumulative_prompt_tokens=self.prompt_tokens,
                cumulative_completion_tokens=self.completion_tokens,
            )

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        parent_run_id = kwargs.get("parent_run_id")
        run_key = str(run_id) if run_id else None
        parent_key = str(parent_run_id) if parent_run_id else None
        if parent_key and parent_key in self._active_tools:
            # Nested tool: remember its id too so grandchild tools are ignored.
            if run_key:
                self._active_tools.add(run_key)
            return
        self.tool_calls += 1
        if run_key:
            self._active_tools.add(run_key)
        if self.trace:
            self.trace.tool_start(tool=serialized.get("name", "unknown"))

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        if run_id:
            self._active_tools.discard(str(run_id))

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        parent_run_id = kwargs.get("parent_run_id")
        run_key = str(run_id) if run_id else None
        parent_key = str(parent_run_id) if parent_run_id else None
        if not parent_key or parent_key not in self._active_tools:
            self.tool_errors += 1
            if self.trace:
                serialized = kwargs.get("serialized") or {}
                self.trace.tool_error(tool=serialized.get("name", "unknown"), error_type=type(error).__name__)
        if run_key:
            self._active_tools.discard(run_key)
