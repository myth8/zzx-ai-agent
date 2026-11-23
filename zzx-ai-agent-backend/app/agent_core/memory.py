"""Agent memory: the system prompt plus the ordered ReAct steps."""
from dataclasses import dataclass, field
from typing import Any

from .types import ActionOutput, ChatMessage, MessageRole, Timing, TokenUsage, ToolCall


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
    """Ordered memory used to rebuild the model context on every step."""

    def __init__(self, system_prompt: str):
        self.system_prompt = SystemPromptStep(system_prompt=system_prompt)
        self.steps: list[Any] = []

    def reset(self) -> None:
        self.steps = []

    def to_messages(self) -> list[ChatMessage]:
        messages = self.system_prompt.to_messages()
        for step in self.steps:
            messages.extend(step.to_messages())
        return messages

    def append(self, step: Any) -> None:
        self.steps.append(step)
