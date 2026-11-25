"""Agent memory: the system prompt plus the ordered ReAct steps."""
from dataclasses import dataclass, field
from typing import Any

from .types import ActionOutput, ChatMessage, MessageRole, Timing, TokenUsage, ToolCall
from .utils import truncate_content


@dataclass
class TaskStep:
    task: str

    def to_messages(self) -> list[ChatMessage]:
        return [ChatMessage(role=MessageRole.USER, content=f"New task:\n{self.task}")]


@dataclass
class SystemPromptStep:
    system_prompt: str

    def to_messages(self) -> list[ChatMessage]:
        return [ChatMessage(role=MessageRole.SYSTEM, content=self.system_prompt)]


@dataclass
class ActionStep:
    """One Thought -> Action -> Observation cycle."""

    step_number: int
    timing: Timing = field(default_factory=Timing)
    model_input_messages: list[ChatMessage] | None = None
    model_output_message: ChatMessage | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_responses: list[ChatMessage] = field(default_factory=list)
    observations: str | None = None
    code_action: str | None = None
    action_output: Any = None
    is_final_answer: bool = False
    error: Exception | None = None
    token_usage: TokenUsage | None = None

    def to_messages(self) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        if self.model_output_message is not None:
            messages.append(self.model_output_message)
        messages.extend(self.tool_responses)
        # CodeAgent stores its observation separately instead of a tool message.
        if self.observations is not None and not self.tool_responses:
            messages.append(
                ChatMessage(role=MessageRole.USER, content=f"Observation:\n{self.observations}")
            )
        if self.error is not None:
            messages.append(
                ChatMessage(
                    role=MessageRole.USER,
                    content=(
                        "Error:\n"
                        f"{self.error}\n"
                        "Take care not to repeat the same mistake. "
                        "If you have retried several times, use a completely different approach."
                    ),
                )
            )
        return messages


@dataclass
class FinalAnswerStep:
    output: Any


class AgentMemory:
    """Ordered memory used to rebuild the model context on every step.

    The first version replayed every step forever, which is simple but makes
    prompt size grow without bound. This version borrows the context-control
    idea from smolagents (bounded observations) and adds a deterministic
    per-run budget: keep the task and the most recent steps, omit older whole
    steps, and truncate over-long individual messages.

    Whole steps are dropped instead of individual tool messages, so a
    ToolCalling assistant tool_call is never separated from its tool response.
    """

    def __init__(self, system_prompt: str):
        self.system_prompt = SystemPromptStep(system_prompt=system_prompt)
        self.steps: list[Any] = []
        self.last_context_stats: dict[str, Any] = {}

    def reset(self) -> None:
        self.steps = []
        self.last_context_stats = {}

    def to_messages(
        self,
        *,
        max_chars: int | None = None,
        keep_recent_steps: int | None = None,
        max_message_chars: int | None = None,
    ) -> list[ChatMessage]:
        task_steps = [step for step in self.steps if isinstance(step, TaskStep)]
        action_steps = [step for step in self.steps if isinstance(step, ActionStep)]
        keep = max(1, keep_recent_steps) if keep_recent_steps else len(action_steps)
        selected = action_steps[-keep:]
        omitted = len(action_steps) - len(selected)
        truncated_messages = 0

        def build(selected_steps: list[ActionStep], omitted_steps: int):
            nonlocal truncated_messages
            messages: list[ChatMessage] = self.system_prompt.to_messages()
            for task_step in task_steps:
                messages.extend(task_step.to_messages())
            if omitted_steps:
                messages.append(
                    ChatMessage(
                        role=MessageRole.USER,
                        content=(
                            "[上下文压缩] 为控制上下文长度，已省略较早的 "
                            f"{omitted_steps} 个执行步骤。请基于任务和最近步骤继续。"
                        ),
                    )
                )
            for step in selected_steps:
                messages.extend(step.to_messages())

            truncated_messages = 0
            if max_message_chars:
                compacted: list[ChatMessage] = []
                for message in messages:
                    content = message.content
                    if (
                        message.role != MessageRole.SYSTEM
                        and isinstance(content, str)
                        and len(content) > max_message_chars
                    ):
                        content = truncate_content(content, max_length=max_message_chars)
                        truncated_messages += 1
                    compacted.append(
                        ChatMessage(
                            role=message.role,
                            content=content,
                            tool_calls=message.tool_calls,
                            tool_call_id=message.tool_call_id,
                            token_usage=message.token_usage,
                        )
                    )
                messages = compacted
            return messages

        messages = build(selected, omitted)
        while (
            max_chars
            and sum(len(message.content or "") for message in messages) > max_chars
            and len(selected) > 1
        ):
            selected = selected[1:]
            omitted += 1
            messages = build(selected, omitted)

        total_chars = sum(len(message.content or "") for message in messages)
        self.last_context_stats = {
            "messages": len(messages),
            "chars": total_chars,
            "action_steps": len(action_steps),
            "kept_steps": len(selected),
            "omitted_steps": omitted,
            "truncated_messages": truncated_messages,
            "max_chars": max_chars,
        }
        return messages

    def append(self, step: Any) -> None:
        self.steps.append(step)
