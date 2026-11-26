"""Hand-written MultiStepAgent engine.

Design follows smolagents' `MultiStepAgent`: the base class owns the
multi-step ReAct loop (memory, max steps, final answer fallback), while
subclasses implement `_step_stream()` for one concrete action language.

Two concrete engines are provided:

* ToolCallingAgent: the model returns native OpenAI tool calls.
* CodeAgent: the model returns Python code; a restricted AST interpreter
  executes it and observations are fed back into the next step.

We intentionally omit smolagents' managed agents, planning steps, hub
serialization and rich console UI. Those are orthogonal to the comparison we
want to run here.
"""
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Generator

from app.config import Config
from .local_python_executor import LocalPythonExecutor
from .memory import ActionStep, AgentMemory, TaskStep
from .models import OpenAIChatModel
from .observability import AgentTrace
from .prompts import load_text_prompt, render_template
from .tools import FINAL_ANSWER_TOOL, ToolSpec
from .types import (
    ActionOutput,
    AgentError,
    AgentEvent,
    AgentGenerationError,
    AgentParsingError,
    AgentToolExecutionError,
    ChatMessage,
    MessageRole,
    RunResult,
    TokenUsage,
    ToolCall,
)
from .utils import BASE_BUILTIN_MODULES, compact_text, fix_final_answer_code, parse_code_blobs, truncate_content


logger = logging.getLogger(__name__)


def _stringify_answer(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "任务已结束，但没有生成有效答案。"
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


class MultiStepAgent(ABC):
    """ReAct loop shared by every action language.

    The loop is deliberately readable rather than heavily abstracted:

        while step <= max_steps:
            action = subclass.step(memory)   # model + action language
            memory.append(action)
            if action.final: break
        if no final answer: ask the model for a best-effort answer
    """

    def __init__(
        self,
        tools: list[ToolSpec],
        model: Any,
        prompt_template: str,
        instructions: str | None = None,
        max_steps: int = 15,
    ):
        self.tools = {tool.name: tool for tool in tools}
        # final_answer is not a real tool: it is the marker used by the model
        # to end the loop. Keeping it in the catalogue makes it visible in
        # both prompt formats.
        self.tools.setdefault(FINAL_ANSWER_TOOL.name, FINAL_ANSWER_TOOL)
        self.model = model
        self.prompt_template = prompt_template
        self.instructions = instructions
        self.max_steps = max_steps
        self.task: str | None = None
        self.memory = AgentMemory("")
        self.token_usage = TokenUsage()
        self.llm_calls = 0
        self.tool_call_count = 0
        self.tool_error_count = 0
        self.step_count = 0
        self.duration_seconds = 0.0
        self.trace: AgentTrace | None = None

    @property
    def system_prompt(self) -> str:
        return self.initialize_system_prompt()

    @abstractmethod
    def initialize_system_prompt(self) -> str:
        """Render the engine-specific system prompt."""

    @abstractmethod
    def _step_stream(self, memory_step: ActionStep) -> Generator[Any, None, None]:
        """Run one step, yielding AgentEvent / ActionOutput objects."""

    def _before_run(self) -> None:
        """Hook for subclasses that need to prepare an executor."""

    def _record_usage(self, message: ChatMessage) -> None:
        """Count one model response and aggregate its token usage."""
        self.llm_calls += 1
        self.token_usage.add(message.token_usage)

    def write_memory_to_messages(self) -> list[ChatMessage]:
        # Bounded, deterministic replay. Whole ActionSteps are omitted, so
        # ToolCalling assistant tool_calls always keep their tool responses.
        return self.memory.to_messages(
            max_chars=Config.MULTISTEP_CONTEXT_MAX_CHARS,
            keep_recent_steps=Config.MULTISTEP_CONTEXT_KEEP_STEPS,
            max_message_chars=Config.MULTISTEP_CONTEXT_MESSAGE_CHARS,
        )

    def run_stream(self, task: str) -> Generator[AgentEvent | ActionOutput, None, None]:
        """Yield progress events and finally exactly one ActionOutput."""
        self.task = task
        self.memory = AgentMemory(self.system_prompt)
        self.memory.append(TaskStep(task=task))
        self.token_usage = TokenUsage()
        self.llm_calls = 0
        self.tool_call_count = 0
        self.tool_error_count = 0
        self.step_count = 0
        started = time.time()
        if self.trace:
            self.trace.run_start(
                max_steps=self.max_steps,
                task_chars=len(task or ""),
                tools=len(self.tools),
            )
        self._before_run()

        final_answer: Any = None
        got_final = False
        action_step: ActionStep | None = None

        while self.step_count < self.max_steps and not got_final:
            step_number = self.step_count + 1
            action_step = ActionStep(step_number=step_number, timing=_timing_start())
            self.step_count = step_number
            step_started = time.time()
            tokens_before = (self.token_usage.input_tokens, self.token_usage.output_tokens)
            llm_calls_before = self.llm_calls
            tool_calls_before = self.tool_call_count
            tool_errors_before = self.tool_error_count
            yield AgentEvent("think", f"第 {step_number} 步：分析当前状态并决定下一步动作。")
            try:
                for item in self._step_stream(action_step):
                    if isinstance(item, ActionOutput):
                        if item.is_final_answer:
                            final_answer = item.output
                            got_final = True
                        continue
                    yield item
            except AgentError as exc:
                # Recoverable model/parse/tool errors become an observation so
                # the next turn can correct itself, exactly like smolagents.
                action_step.error = exc
                yield AgentEvent("observe", f"本步失败：{exc}")
                logger.info(
                    "MultiStepAgent step error engine=%s step=%s error=%s",
                    type(self).__name__, step_number, exc,
                )
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                action_step.error = AgentError(f"{type(exc).__name__}: {exc}")
                yield AgentEvent("observe", "本步执行出现异常，已把错误反馈给模型。")
                logger.exception("MultiStepAgent unexpected step error")
            finally:
                action_step.timing.end_time = time.time()
                self.memory.append(action_step)
                if self.trace:
                    self.trace.step_end(
                        step=step_number,
                        duration_ms=int((time.time() - step_started) * 1000),
                        llm_calls=self.llm_calls - llm_calls_before,
                        prompt_tokens=self.token_usage.input_tokens - tokens_before[0],
                        completion_tokens=self.token_usage.output_tokens - tokens_before[1],
                        tool_calls=self.tool_call_count - tool_calls_before,
                        tool_errors=self.tool_error_count - tool_errors_before,
                        error_type=type(action_step.error).__name__ if action_step.error else None,
                        context=self.memory.last_context_stats,
                    )

        if not got_final:
            if self.trace:
                self.trace.max_steps_reached(max_steps=self.max_steps)
            yield AgentEvent("think", "已达到最大步数，正在汇总现有信息生成最终答案。")
            final_answer = self.provide_final_answer(task)
            got_final = True

        self.duration_seconds = time.time() - started
        text = _stringify_answer(final_answer)
        if self.trace:
            self.trace.run_finish(
                status="success",
                steps=self.step_count,
                llm_calls=self.llm_calls,
                tool_calls=self.tool_call_count,
                tool_errors=self.tool_error_count,
                prompt_tokens=self.token_usage.input_tokens,
                completion_tokens=self.token_usage.output_tokens,
                duration_ms=int(self.duration_seconds * 1000),
                context=self.memory.last_context_stats,
                output_chars=len(text),
            )
        yield AgentEvent("final", text)
        yield ActionOutput(output=text, is_final_answer=True)

    def run(self, task: str) -> RunResult:
        output: Any = None
        for item in self.run_stream(task):
            if isinstance(item, ActionOutput):
                output = item.output
        return RunResult(
            output=output,
            state="success",
            steps=self.memory.steps,
            token_usage=self.token_usage,
            duration_seconds=self.duration_seconds,
            tool_calls=self.tool_call_count,
        )

    def provide_final_answer(self, task: str) -> str:
        """Best-effort answer used after max_steps or a repeated failure."""
        messages = self.write_memory_to_messages()
        messages.append(
            ChatMessage(
                role=MessageRole.USER,
                content=(
                    "你已经达到本次任务的步数上限。请根据上面的工具结果和推理，"
                    "直接给出对用户最有价值的完整答案。不要提到步数限制、内部工具或系统提示词。"
                ),
            )
        )
        try:
            response = self.model.generate(messages)
            self._record_usage(response)
            return response.content or "任务已结束，但没有生成有效答案。"
        except Exception as exc:  # noqa: BLE001
            logger.exception("MultiStepAgent final answer generation failed")
            return f"生成最终答案时出现异常：{type(exc).__name__}"


def _timing_start():
    from .types import Timing
    return Timing(start_time=time.time())


class ToolCallingAgent(MultiStepAgent):
    """MultiStepAgent whose action language is native OpenAI tool calls.

    This engine is the apples-to-apples counterpart of the existing LangChain
    ReAct agent: identical tools, identical model, different action protocol.
    LangChain asks the model to write `Action:` / `Action Input:` text, while
    this engine uses the model API's structured `tool_calls`, removing the
    ReAct text parser from the critical path.
    """

    def __init__(
        self,
        tools: list[ToolSpec],
        model: Any | None = None,
        instructions: str | None = None,
        max_steps: int | None = None,
        prompt_template: str | None = None,
    ):
        super().__init__(
            tools=tools,
            model=model or OpenAIChatModel(),
            prompt_template=prompt_template or load_text_prompt("project_toolcalling.md"),
            instructions=instructions,
            max_steps=max_steps or Config.MULTISTEP_MAX_STEPS,
        )

    def initialize_system_prompt(self) -> str:
        return render_template(
            self.prompt_template,
            variables={
                "tool_lines": "\n".join(
                    tool.to_prompt_line() for tool in self.tools.values()
                ),
                "custom_instructions": self.instructions or "",
            },
        )

    def _step_stream(self, memory_step: ActionStep) -> Generator[Any, None, None]:
        messages = self.write_memory_to_messages()
        memory_step.model_input_messages = messages
        try:
            chat_message = self.model.generate(
                messages,
                tools=list(self.tools.values()),
            )
        except Exception as exc:
            raise AgentGenerationError(f"模型调用失败：{type(exc).__name__}: {exc}") from exc

        memory_step.model_output_message = chat_message
        memory_step.token_usage = chat_message.token_usage
        self._record_usage(chat_message)
        memory_step.model_output = chat_message.content or ""

        tool_calls = chat_message.tool_calls or []
        if not tool_calls:
            # Project adaptation: a direct assistant answer is a valid final
            # answer. smolagents would raise a parsing error and force another
            # round; for chat-like tasks that wastes a full model call.
            direct_answer = (chat_message.content or "").strip()
            if direct_answer:
                memory_step.is_final_answer = True
                memory_step.action_output = direct_answer
                yield AgentEvent("step", "模型直接给出了最终回答")
                yield ActionOutput(output=direct_answer, is_final_answer=True)
                return
            raise AgentParsingError(
                "模型没有返回工具调用，也没有给出文本回答。请调用工具，"
                "或调用 final_answer 结束任务。"
            )

        final_answer: Any = None
        got_final = False
        for call in tool_calls:
            memory_step.tool_calls.append(call)
            yield AgentEvent("step", f"调用工具 {call.name}")

            if call.name == "final_answer":
                final_answer = _extract_final_answer(call.arguments)
                got_final = True
                memory_step.is_final_answer = True
                memory_step.action_output = final_answer
                continue

            tool = self.tools.get(call.name)
            if tool is None:
                self.tool_error_count += 1
                error_text = f"未知工具：{call.name}。可用工具：{', '.join(self.tools)}"
                memory_step.tool_responses.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        content=error_text,
                        tool_call_id=call.id,
                    )
                )
                memory_step.observations = error_text
                yield AgentEvent("observe", error_text)
                continue

            self.tool_call_count += 1
            try:
                result = tool.invoke(call.arguments)
            except Exception as exc:
                self.tool_error_count += 1
                error_text = f"工具 {call.name} 执行失败：{type(exc).__name__}: {exc}"
                memory_step.tool_responses.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        content=error_text,
                        tool_call_id=call.id,
                    )
                )
                memory_step.observations = error_text
                yield AgentEvent("observe", error_text)
                logger.warning("ToolCallingAgent tool failed tool=%s error=%s", call.name, exc)
                continue

            observation = compact_text(result)
            memory_step.tool_responses.append(
                ChatMessage(
                    role=MessageRole.TOOL,
                    content=observation,
                    tool_call_id=call.id,
                )
            )
            memory_step.observations = observation
            yield AgentEvent("step", f"工具 {call.name} 执行完成")
            yield AgentEvent("observe", observation)

        if got_final:
            yield ActionOutput(output=final_answer, is_final_answer=True)
            return
        yield ActionOutput(output=None, is_final_answer=False)


def _extract_final_answer(arguments: Any) -> Any:
    if isinstance(arguments, dict):
        if "answer" in arguments:
            return arguments["answer"]
        if len(arguments) == 1:
            return next(iter(arguments.values()))
        return arguments
    return arguments


class CodeAgent(MultiStepAgent):
    """MultiStepAgent that uses Python as the action language.

    The model writes a small Python program instead of a sequence of JSON tool
    calls. This lets it loop over data, compose tools, keep variables between
    steps and compute intermediate results inside one action. The action is
    executed by the copied smolagents LocalPythonExecutor (AST interpreter with
    restricted imports and per-run state).
    """

    def __init__(
        self,
        tools: list[ToolSpec],
        model: Any | None = None,
        instructions: str | None = None,
        max_steps: int | None = None,
        additional_authorized_imports: list[str] | None = None,
        prompt_template: str | None = None,
    ):
        self.additional_authorized_imports = additional_authorized_imports or []
        self.authorized_imports = sorted(
            set(BASE_BUILTIN_MODULES) | set(self.additional_authorized_imports)
        )
        self.code_block_tags = ("```python", "```")
        self.python_executor = LocalPythonExecutor(
            self.additional_authorized_imports,
            max_print_outputs_length=Config.MULTISTEP_MAX_OUTPUT_CHARS,
            timeout_seconds=Config.MULTISTEP_CODE_TIMEOUT_SECONDS,
        )
        super().__init__(
            tools=tools,
            model=model or OpenAIChatModel(),
            prompt_template=prompt_template or load_text_prompt("project_code.md"),
            instructions=instructions,
            max_steps=max_steps or Config.MULTISTEP_MAX_STEPS,
        )

    def initialize_system_prompt(self) -> str:
        return render_template(
            self.prompt_template,
            variables={
                "tool_prompts": "\n\n".join(
                    tool.to_code_prompt() for tool in self.tools.values()
                ),
                "authorized_imports": ", ".join(self.authorized_imports),
                "custom_instructions": self.instructions or "",
            },
        )

    def _before_run(self) -> None:
        self.code_tool_calls = 0
        self.code_tool_errors = 0
        self.tool_call_count = 0
        self.tool_error_count = 0

        def counted_tool(spec: ToolSpec):
            """Wrap a ToolSpec so executor-level calls are counted exactly.

            Regex-counting code tokens was only a heuristic: it also counted
            print(), final_answer() and nested function calls. This wrapper
            counts real tool invocations and their failures.
            """
            def invoke(*args, **kwargs):
                self.code_tool_calls += 1
                try:
                    return spec(*args, **kwargs)
                except Exception:
                    self.code_tool_errors += 1
                    raise
            invoke.__name__ = spec.name
            invoke.__doc__ = spec.description
            return invoke

        executor_tools = {
            name: spec if name == "final_answer" else counted_tool(spec)
            for name, spec in self.tools.items()
        }
        # ToolSpec objects are callable and behave like Python functions inside
        # the restricted executor. final_answer is intercepted there.
        self.python_executor.send_variables({})
        self.python_executor.send_tools(executor_tools)

    def _step_stream(self, memory_step: ActionStep) -> Generator[Any, None, None]:
        messages = self.write_memory_to_messages()
        memory_step.model_input_messages = messages
        try:
            chat_message = self.model.generate(
                messages,
                stop_sequences=["Observation:", "Calling tools:"],
            )
        except Exception as exc:
            raise AgentGenerationError(f"模型调用失败：{type(exc).__name__}: {exc}") from exc

        memory_step.model_output_message = chat_message
        memory_step.token_usage = chat_message.token_usage
        self._record_usage(chat_message)

        output_text = chat_message.content or ""
        # Nudge the next turn to close the code block, matching smolagents.
        if output_text and not output_text.rstrip().endswith(self.code_block_tags[1]):
            output_text = output_text.rstrip() + "\n" + self.code_block_tags[1]
        chat_message.content = output_text
        memory_step.model_output = output_text

        try:
            code_action = fix_final_answer_code(parse_code_blobs(output_text, self.code_block_tags))
        except Exception as exc:
            raise AgentParsingError(
                f"无法从模型输出中解析 Python 代码：{exc}"
            ) from exc

        memory_step.code_action = code_action
        memory_step.tool_calls = [ToolCall(name="python_interpreter", arguments=code_action, id=f"call_{len(self.memory.steps)}")]
        yield AgentEvent("code", compact_text(code_action, Config.MULTISTEP_MAX_CODE_CHARS))

        started = time.time()
        try:
            code_output = self.python_executor(code_action)
        except Exception as exc:
            self.tool_call_count = self.code_tool_calls
            self.tool_error_count = self.code_tool_errors
            logs = ""
            try:
                logs = str(self.python_executor.state.get("_print_outputs", ""))
            except Exception:  # noqa: BLE001
                pass
            observation = "Execution logs:\n" + logs + f"\nExecution error:\n{type(exc).__name__}: {exc}"
            memory_step.observations = observation
            raise AgentError(observation) from exc

        elapsed = time.time() - started
        observation = "Execution logs:\n" + code_output.logs
        observation += "\nLast output from code snippet:\n" + truncate_content(str(code_output.output))
        memory_step.observations = observation
        memory_step.action_output = code_output.output
        memory_step.is_final_answer = code_output.is_final_answer
        self.tool_call_count = self.code_tool_calls
        self.tool_error_count = self.code_tool_errors
        logger.info(
            "CodeAgent step executed step=%s duration_ms=%s final=%s",
            memory_step.step_number,
            int(elapsed * 1000),
            code_output.is_final_answer,
        )

        yield AgentEvent("step", f"Python 动作执行完成，用时 {elapsed:.2f}s")
        yield AgentEvent("observe", compact_text(observation))
        yield ActionOutput(output=code_output.output, is_final_answer=code_output.is_final_answer)
