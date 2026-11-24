"""OpenAI-compatible chat model used by MultiStepAgent.

The existing LangChain path uses ChatOpenAI. To keep the two engines
independent, this adapter talks to the OpenAI-compatible DeepSeek endpoint
directly through the official `openai` SDK. The interface is intentionally
small: `generate(messages, stop_sequences, tools)`.
"""
import json
import logging
from typing import Any

from openai import OpenAI

from app.config import Config
from .types import ChatMessage, MessageRole, TokenUsage, ToolCall


logger = logging.getLogger(__name__)


class OpenAIChatModel:
    def __init__(
        self,
        model_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ):
        self.model_id = model_id or Config.MULTISTEP_MODEL
        self.temperature = (
            Config.MULTISTEP_TEMPERATURE if temperature is None else temperature
        )
        self.max_tokens = max_tokens or Config.MULTISTEP_MAX_TOKENS
        self.client = OpenAI(
            api_key=api_key or Config.DEEPSEEK_API_KEY,
            base_url=base_url or Config.DEEPSEEK_API_BASE,
            timeout=timeout or Config.MULTISTEP_TIMEOUT_SECONDS,
            max_retries=2,
        )

    def generate(
        self,
        messages: list[ChatMessage],
        stop_sequences: list[str] | None = None,
        tools: list[Any] | None = None,
    ) -> ChatMessage:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [self._to_openai_message(message) for message in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stop_sequences:
            payload["stop"] = stop_sequences
        if tools:
            payload["tools"] = [tool.to_openai_schema() for tool in tools]
            payload["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**payload)
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        for index, raw_call in enumerate(message.tool_calls or []):
            raw_arguments = raw_call.function.arguments
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                # Keep the raw string: ToolSpec._coerce_arguments will try again
                # and otherwise the agent will receive a useful parsing error.
                arguments = raw_arguments
            tool_calls.append(
                ToolCall(
                    name=raw_call.function.name,
                    arguments=arguments,
                    id=raw_call.id or f"call_{index}",
                )
            )

        usage = None
        if getattr(response, "usage", None) is not None:
            usage = TokenUsage(
                input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
            )

        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content=message.content,
            tool_calls=tool_calls,
            token_usage=usage,
        )

    @staticmethod
    def _to_openai_message(message: ChatMessage) -> dict[str, Any]:
        if message.role == MessageRole.TOOL:
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id or "",
                "content": message.content or "",
            }
        if message.role == MessageRole.ASSISTANT and message.tool_calls:
            return {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in message.tool_calls
                ],
            }
        return {"role": message.role.value, "content": message.content or ""}
