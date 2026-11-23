"""Small helpers shared by the hand-written agent engine.

The code-block parsing and truncation logic is adapted from smolagents
(`smolagents/utils.py`, Apache-2.0). Keeping the original behaviour makes the
new engine easy to compare with the reference implementation.
"""
import ast
import json
import re
import textwrap
from typing import Any


# Modules the CodeAgent may import without extra configuration. This mirrors
# smolagents' BASE_BUILTIN_MODULES and deliberately excludes os/sys/subprocess.
BASE_BUILTIN_MODULES = [
    "collections",
    "datetime",
    "itertools",
    "math",
    "queue",
    "random",
    "re",
    "stat",
    "statistics",
    "time",
    "unicodedata",
]

MAX_LENGTH_TRUNCATE_CONTENT = 20000


def truncate_content(content: str, max_length: int = MAX_LENGTH_TRUNCATE_CONTENT) -> str:
    """Keep head and tail so the observation stays useful but bounded."""
    content = str(content)
    if len(content) <= max_length:
        return content
    return (
        content[: max_length // 2]
        + f"\n..._This content has been truncated to stay below {max_length} characters_...\n"
        + content[-max_length // 2 :]
    )


def extract_code_from_text(text: str, code_block_tags: tuple[str, str]) -> str | None:
    """Extract every code block between the configured opening/closing tags."""
    pattern = rf"{code_block_tags[0]}(.*?){code_block_tags[1]}"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return "\n\n".join(match.strip() for match in matches)
    return None


def parse_code_blobs(text: str, code_block_tags: tuple[str, str] = ("```python", "```")) -> str:
    """Extract executable code from a model answer.

    This is copied from smolagents so CodeAgent behaves like the reference:
    1. look for the configured tags;
    2. fall back to markdown ```python / ``` fences;
    3. accept a bare Python snippet;
    4. otherwise raise a helpful parsing error.
    """
    matches = extract_code_from_text(text, code_block_tags)
    if not matches:
        matches = extract_code_from_text(text, ("```(?:python|py)", "\n```"))
    if matches:
        return matches
    try:
        ast.parse(text)
        return text
    except SyntaxError:
        pass

    if "final" in text and "answer" in text:
        raise ValueError(
            textwrap.dedent(
                f"""
                Your code snippet is invalid, because the regex pattern {code_block_tags[0]}(.*?){code_block_tags[1]} was not found in it.
                Here is your code snippet:
                {text}
                It seems like you're trying to return the final answer, you can do it as follows:
                {code_block_tags[0]}
                final_answer("YOUR FINAL ANSWER HERE")
                {code_block_tags[1]}
                """
            ).strip()
        )
    raise ValueError(
        textwrap.dedent(
            f"""
            Your code snippet is invalid, because the regex pattern {code_block_tags[0]}(.*?){code_block_tags[1]} was not found in it.
            Here is your code snippet:
            {text}
            Make sure to include code with the correct pattern, for instance:
            Thought: Your thoughts
            {code_block_tags[0]}
            # Your python code here
            {code_block_tags[1]}
            """
        ).strip()
    )


def fix_final_answer_code(code: str) -> str:
    """Prevent `final_answer = ...` from shadowing the final_answer tool."""
    assignment_pattern = r"(?<!\.)(?<!\w)\bfinal_answer\s*="
    if "final_answer(" not in code or not re.search(assignment_pattern, code):
        return code
    code = re.sub(r"(?<!\.)(?<!\w)(\bfinal_answer)(\s*=)", r"final_answer_variable\2", code)
    return re.sub(r"(?<!\.)(?<!\w)(\bfinal_answer\b)(?!\s*\()", "final_answer_variable", code)


def make_json_safe(value: Any) -> Any:
    """Best-effort conversion for SSE metadata / debug logs."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def compact_text(value: Any, max_length: int = 4000) -> str:
    """Collapse long tool output for the browser while keeping the head."""
    text = truncate_content(str(value).strip(), max_length=max_length)
    return text
