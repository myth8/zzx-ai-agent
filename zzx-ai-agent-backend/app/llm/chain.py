"""
Chain 实现
==========
简单的 Prompt → LLM → 文本流水线。
使用方式：make_chain(system_prompt) → stream_chain(chain, message)

数据流：
  ChatPromptTemplate (system + user) → ChatOpenAI → StrOutputParser → 文本块
"""
import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.llm import llm

logger = logging.getLogger(__name__)


def make_chain(system_prompt, context=""):
    """
    构建 LangChain LCEL 链：
      prompt_template | llm | string_parser

    参数：
        system_prompt: AI 的角色指令。
        context:       对话历史（摘要 + 最近消息）。

    返回：
        可用的 Runnable 链（可使用 .stream() / .invoke()）
    """
    human_template = "{input}"
    if context:
        human_template = "【对话历史】\n{history}\n\n---\n\n{input}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_template),
        ])
        # 返回同时接受 input 和 history 的链
        return prompt | llm | StrOutputParser()

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_template),
    ])
    return prompt | llm | StrOutputParser()


def stream_chain(
    chain, message, context="", user_id=None, session_id="", llm_ref=None
):
    """
    同步流式输出，实时记录每个 token 块。

    参数：
        chain: make_chain() 返回的 Runnable
        message: 用户输入的字符串
        context: 对话历史字符串（可选）
        session_id: 用于流结束后保存消息（可选）
        llm_ref: 用于生成摘要的 LLM 实例（可选）

    产出：
        str: LLM 输出的 token 级别文本块
    """
    logger.info(
        "Chain started session=%s input_chars=%s",
        session_id or "-",
        len(message),
    )
    final_answer = ''

    invoke_input = {"input": message}
    if context:
        invoke_input["history"] = context

    for chunk in chain.stream(invoke_input):
        if chunk:
            # print(f"[Chain Token] {chunk}\n", end="", flush=True)
            final_answer += chunk
            yield chunk

    logger.info(
        "Chain completed session=%s output_chars=%s",
        session_id or "-",
        len(final_answer),
    )

    # 如果提供了 session_id，则保存消息并触发摘要生成
    if session_id:
        try:
            from app.chat_history import save_message, update_summary
            save_message(user_id, session_id, "assistant", final_answer)
            if llm_ref:
                update_summary(user_id, session_id)
        except Exception:
            logger.exception("Chain result persistence failed session=%s", session_id)
