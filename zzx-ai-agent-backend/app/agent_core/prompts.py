"""Prompt loading for the project-adapted MultiStepAgent engines.

The first version of these engines copied smolagents' YAML prompts verbatim.
That preserved behaviour but also carried large few-shot examples, planning
blocks and managed-agent instructions that this project does not use. The
current templates are deliberately project-specific and much shorter:
tools, skills, Chinese output, and the current tool catalogue only.
"""
from pathlib import Path
from typing import Any

from jinja2 import StrictUndefined, Template


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def load_text_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def render_template(template: str, variables: dict[str, Any]) -> str:
    # StrictUndefined turns a forgotten variable into a clear startup error
    # instead of silently generating a broken system prompt.
    return Template(template, undefined=StrictUndefined).render(**variables)
