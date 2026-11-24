"""Tool abstraction shared by ToolCallingAgent and CodeAgent.

The goal is parity with the existing LangChain tools: a ToolSpec can wrap any
LangChain `BaseTool`, so a benchmark can run the same tool implementation under
the LangChain ReAct engine and the new MultiStepAgent engines.
"""
import json
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable


_TYPE_ALIASES = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
    "null": "None",
}


@dataclass
class ToolSpec:
    name: str
    description: str
    inputs: dict[str, dict] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    output_type: str = "string"
    func: Callable[..., Any] | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the underlying callable.

        Positional arguments are accepted because the Python executor wraps
        `final_answer(value)` and calls the registered callable positionally.
        `final_answer` is represented without a callable: the executor
        intercepts it and raises FinalAnswerException with the answer value.
        """
        if args:
            kwargs = self._coerce_arguments(args[0] if len(args) == 1 else args)
        if self.func is None:
            if self.name == "final_answer":
                return kwargs.get("answer", kwargs)
            raise RuntimeError(f"Tool {self.name} has no implementation")
        return self.func(**kwargs)

    def invoke(self, arguments: Any) -> Any:
        arguments = self._coerce_arguments(arguments)
        if self.func is None:
            if self.name == "final_answer":
                return arguments.get("answer", arguments)
            raise RuntimeError(f"Tool {self.name} has no implementation")
        return self.func(**arguments)

    def _coerce_arguments(self, arguments: Any) -> dict[str, Any]:
        """Accept native JSON objects and the single-string fallback some models emit."""
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            stripped = arguments.strip()
            if stripped.startswith("{"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
            if len(self.inputs) == 1:
                return {next(iter(self.inputs)): arguments}
            if self.name == "final_answer":
                return {"answer": arguments}
            return {"input": arguments}
        if len(self.inputs) == 1:
            return {next(iter(self.inputs)): arguments}
        if isinstance(arguments, (list, tuple)) and len(self.inputs) == len(arguments):
            return dict(zip(self.inputs, arguments))
        raise ValueError(f"Arguments for tool {self.name} must be a JSON object")

    def to_openai_schema(self) -> dict[str, Any]:
        properties = {}
        for key, schema in self.inputs.items():
            item = {
                "type": schema.get("type", "string"),
                "description": schema.get("description") or schema.get("title") or key,
            }
            if "enum" in schema:
                item["enum"] = schema["enum"]
            properties[key] = item
        parameters: dict[str, Any] = {"type": "object", "properties": properties}
        if self.required:
            parameters["required"] = self.required
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            }
        }

    def to_tool_calling_prompt(self) -> str:
        """One-line tool summary for the project ToolCalling prompt."""
        return self.to_prompt_line()

    def to_prompt_line(self) -> str:
        """Compact tool line; full descriptions stay in the API tool schema."""
        args = ", ".join(self.inputs)
        description = " ".join(self.description.strip().split())
        if len(description) > 180:
            description = description[:177] + "..."
        return f"- `{self.name}({args})`: {description}"

    def to_code_prompt(self) -> str:
        """Render a Python-like signature for the CodeAgent prompt."""
        args = ", ".join(
            f"{name}: {_TYPE_ALIASES.get(schema.get('type', 'string'), 'str')}"
            for name, schema in self.inputs.items()
        )
        signature = f"def {self.name}({args}) -> {self.output_type}:"
        doc = self.description
        if self.inputs:
            args_doc = "\n".join(
                f"{name}: {schema.get('description') or schema.get('title') or name}"
                for name, schema in self.inputs.items()
            )
            doc += f"\n\nArgs:\n{textwrap.indent(args_doc, '    ')}"
        body = textwrap.indent(f'"""{doc}\n"""', "    ")
        return f"{signature}\n{body}"


def _schema_from_langchain_tool(tool: Any) -> tuple[dict[str, dict], list[str]]:
    """Read an OpenAI-compatible argument schema from a LangChain tool."""
    properties: dict[str, dict] = {}
    required: list[str] = []
    schema_obj = getattr(tool, "args_schema", None)
    if schema_obj is not None and hasattr(schema_obj, "model_json_schema"):
        try:
            schema = schema_obj.model_json_schema()
            properties = schema.get("properties", {}) or {}
            required = list(schema.get("required", []) or [])
        except Exception:
            properties = {}
    if not properties:
        for name, type_info in (getattr(tool, "args", {}) or {}).items():
            type_name = type_info.get("type", "string") if isinstance(type_info, dict) else "string"
            properties[name] = {"type": type_name, "description": name}
            required.append(name)
    return properties, required


def tool_spec_from_langchain(tool: Any) -> ToolSpec:
    properties, required = _schema_from_langchain_tool(tool)
    description = getattr(tool, "description", "") or getattr(tool, "name", "")

    def _invoke(**kwargs: Any) -> Any:
        # LangChain BaseTool.invoke accepts a dict and handles validation,
        # coercion and ToolException conversion for us.
        return tool.invoke(kwargs)

    return ToolSpec(
        name=getattr(tool, "name", tool.__class__.__name__),
        description=description,
        inputs=properties,
        required=required,
        output_type="string",
        func=_invoke,
    )


def build_tool_specs(langchain_tools: list[Any]) -> dict[str, ToolSpec]:
    return {tool.name: tool_spec_from_langchain(tool) for tool in langchain_tools}


FINAL_ANSWER_TOOL = ToolSpec(
    name="final_answer",
    description=(
        "Provide the final answer to the user's task. "
        "This is the only way to finish the task; otherwise the loop continues."
    ),
    inputs={"answer": {"type": "string", "description": "The complete final answer for the user."}},
    required=["answer"],
    output_type="string",
    func=None,
)
