"""Core data types for the MultiStepAgent engine.

The layout follows smolagents' AgentMemory / ChatMessage design, but only the
parts needed by this project are implemented. That keeps the control flow
recognisable to readers who know smolagents while avoiding the extra
serialization, hub and managed-agent plumbing.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentError(Exception):
    """Base class for recoverable agent loop errors."""


class AgentGenerationError(AgentError):
    """The model call itself failed."""


class AgentParsingError(AgentError):
    """The model answered but the action could not be parsed."""


class AgentToolExecutionError(AgentError):
    """A tool call failed during execution."""


class AgentMaxStepsError(AgentError):
    """The agent used all allowed steps."""


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    name: str
    arguments: Any
    id: str


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: "TokenUsage | None") -> None:
        if other is None:
            return
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


@dataclass
class ChatMessage:
    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    token_usage: TokenUsage | None = None


@dataclass
class AgentEvent:
    """A user-visible progress event emitted by the step generator."""

    kind: str  # think | code | step | observe | meta
    text: str
    data: dict | None = None


@dataclass
class ActionOutput:
    """Final outcome of one ReAct step."""

    output: Any
    is_final_answer: bool = False


@dataclass
class RunResult:
    output: Any
    state: str
    steps: list[Any]
    token_usage: TokenUsage
    duration_seconds: float
    tool_calls: int


@dataclass
class Timing:
    start_time: float = 0.0
    end_time: float = 0.0
