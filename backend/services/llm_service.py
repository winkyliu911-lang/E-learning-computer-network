import logging
import os
import re

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None
_init_error = None

MAX_HISTORY_MESSAGE_CHARS = 1000


def init_llm_client():
    global _client, _init_error

    api_key = os.environ.get(
        "DASHSCOPE_API_KEY", "sk-45af25c9a2974ae7bbb8fcf87bb01f5e"
    )
    base_url = os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    try:
        _client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(
                base_url=base_url,
                follow_redirects=True,
            ),
        )
        logger.info("LLM client initialized successfully")
    except Exception as e:
        _init_error = str(e)
        logger.error("LLM client init error: %s", _init_error, exc_info=True)
        _client = None


def get_llm_client():
    if _client is None:
        msg = "LLM 客户端未初始化。请检查后端启动日志或 API 客户端初始化配置。"
        if _init_error:
            msg += f" 初始化错误: {_init_error}"
        raise RuntimeError(msg)
    return _client


def trim_text(text, max_chars):
    if not text:
        return ""
    cleaned = str(text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + "..."


def call_qwen_api(question, context="", image_data_urls=None, history_messages=None):
    client = get_llm_client()

    system_prompt = (
        "你是一个专业的计算机网络知识助手，使用中文回答，简明准确，必要时给出示例。"
        "回复时不要使用任何markdown格式，不要使用#号、*号、-号列表等标记符号，"
        "直接用纯文本和数字编号回答。"
    )

    messages = [{"role": "system", "content": system_prompt}]

    if history_messages:
        messages.extend(history_messages)

    user_content = []

    text_parts = []
    if context:
        text_parts.append(f"背景信息：{context}")
    text_parts.append(f"用户问题：{question}")
    user_content.append({"type": "text", "text": "\n\n".join(text_parts)})

    if image_data_urls:
        for url in image_data_urls:
            user_content.append({"type": "image_url", "image_url": {"url": url}})

    messages.append({"role": "user", "content": user_content})

    completion = client.chat.completions.create(
        model="qwen-vl-max",
        messages=messages,
        temperature=0.7,
        max_tokens=1500,
        stream=False,
    )

    answer = (completion.choices[0].message.content or "").strip()
    answer = re.sub(r'<think>[\s\S]*?</think>', '', answer).strip()

    if not answer:
        logger.warning("LLM returned empty response")
        return "❌ 无法解析 LLM 响应，请查看后端日志"

    return answer
