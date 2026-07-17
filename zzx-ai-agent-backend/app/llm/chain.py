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


def make_chain(system_prompt, context=""):
    """
    Build a LangChain LCEL chain:
      prompt_template | llm | string_parser

    Args:
        system_prompt: Role instruction for the AI.
        context:       Conversation history (summary + recent messages).

    Returns:
        A Runnable chain usable with .stream() / .invoke()
    """
    human_template = "{input}"
    if context:
        human_template = "\u3010\u5bf9\u8bdd\u5386\u53f2\u3011\n{history}\n\n---\n\n{input}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_template),
        ])
        # Returns a chain that accepts both input and history
        return prompt | llm | StrOutputParser()

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_template),
    ])
    return prompt | llm | StrOutputParser()


def stream_chain(chain, message, context="", session_id="", llm_ref=None):
    """
    Synchronous streaming with real-time chunk logging.

    Args:
        chain: Runnable returned by make_chain()
        message: User input string.
        context: Conversation history string (optional).
        session_id: For saving messages after stream (optional).
        llm_ref: LLM instance for summary generation (optional).

    Yields:
        str: Token-level text chunks from the LLM.
    """
    print(f"\n{'─'*60}", flush=True)
    print(f"[Chain] session={session_id} | Input: {message}", flush=True)
    print(f"{'─'*60}", flush=True)
    final_answer = ''

    invoke_input = {"input": message}
    if context:
        invoke_input["history"] = context

    for chunk in chain.stream(invoke_input):
        if chunk:
            # print(f"[Chain Token] {chunk}\n", end="", flush=True)
            final_answer += chunk
            yield chunk

    print(f"[Chain] session={session_id} | final_answer: {final_answer[:100]}...", flush=True)
    print("", flush=True)  # trailing newline

    # Save messages and trigger summary if we have a session_id
    if session_id:
        try:
            from app.chat_history import save_message, update_summary
            save_message(session_id, "assistant", final_answer)
            if llm_ref:
                update_summary(session_id)
        except Exception as e:
            print(f"[Chain] save error: {e}", flush=True)
