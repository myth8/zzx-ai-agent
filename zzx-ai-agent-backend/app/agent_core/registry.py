"""Engine identifiers and their persisted `chat_type` values.

Existing sessions store `chat_type='agent'` for the LangChain ReAct engine.
We keep that value for backward compatibility and add two new chat types for
the MultiStepAgent engines. The frontend URL uses friendlier names
(`react`, `toolcalling`, `code`).
"""
ENGINE_CHAT_TYPES = {
    "langchain": "agent",
    "react": "agent",
    "toolcalling": "toolcalling",
    "code": "code",
}

CHAT_TYPE_ENGINES = {
    "agent": "react",
    "toolcalling": "toolcalling",
    "code": "code",
}

ENGINE_LABELS = {
    "react": "LangChain ReAct",
    "toolcalling": "MultiStep · ToolCallingAgent",
    "code": "MultiStep · CodeAgent",
}


def normalize_engine(value: str | None, default: str = "react") -> str:
    key = (value or default).strip().lower()
    if key not in ENGINE_CHAT_TYPES:
        raise ValueError(f"Unknown agent engine: {value}")
    # `langchain` is an alias of `react`.
    return "react" if key == "langchain" else key


def chat_type_for_engine(engine: str) -> str:
    return ENGINE_CHAT_TYPES[normalize_engine(engine)]


def engine_for_chat_type(chat_type: str) -> str | None:
    return CHAT_TYPE_ENGINES.get(chat_type)
