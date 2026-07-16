"""
Chain Implementation
====================
Simple Prompt → LLM → text pipeline.
Use: make_chain(system_prompt) → stream_chain(chain, message)

Data flow:
  ChatPromptTemplate (system + user) → ChatOpenAI → StrOutputParser → text chunks
"""
import sys
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.llm import llm


def make_chain(system_prompt):
    """
    Build a LangChain LCEL chain:
      prompt_template | llm | string_parser

    Args:
        system_prompt: Role instruction for the AI.

    Returns:
        A Runnable chain usable with .stream() / .invoke()
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])
    return prompt | llm | StrOutputParser()


def stream_chain(chain, message):
    """
    Synchronous streaming with real-time chunk logging.

    Args:
        chain: Runnable returned by make_chain()
        message: User input string.

    Yields:
        str: Token-level text chunks from the LLM.
    """
    print(f"\n{'─'*60}", flush=True)
    print(f"[Chain] Input: {message}", flush=True)
    print(f"{'─'*60}", flush=True)
    final_answer = ''
    for chunk in chain.stream({"input": message}):
        if chunk:
            # print(f"[Chain Token] {chunk}\n", end="", flush=True)
            final_answer += chunk
            yield chunk
    print(f"[Chain] final_answer: {final_answer}", flush=True)
    print("", flush=True)  # trailing newline
