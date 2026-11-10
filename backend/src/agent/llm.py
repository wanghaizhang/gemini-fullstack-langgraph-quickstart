"""LLM provider switch (Google 之外的模型也能跑).

环境变量:
  LLM_PROVIDER        google | openai          默认 google（上游行为不变）
  LOCAL_BASE_URL      OpenAI 兼容端点 base_url（或 OPENAI_BASE_URL）
  LOCAL_API_KEY       端点 key（或 OPENAI_API_KEY），本地端点可留空
  STRUCTURED_METHOD   json_mode | function_calling，留空走 langchain 默认

`openai` 分支覆盖所有 OpenAI 兼容端点：OpenAI 官方、Ollama、vLLM、LiteLLM、
DeepSeek、通义/ Kimi 的 OpenAI 兼容接口等 —— 换模型只需改 model 名。
"""

import json
import os
import re
from typing import Any, Optional

from pydantic import BaseModel


def get_provider() -> str:
    """读取时取值（不在 import 时固化）：graph.py 的 load_dotenv() 晚于本模块 import。"""
    return (os.getenv("LLM_PROVIDER") or "google").lower()


def get_base_url() -> Optional[str]:
    return os.getenv("LOCAL_BASE_URL") or os.getenv("OPENAI_BASE_URL")


def get_api_key() -> Optional[str]:
    return os.getenv("LOCAL_API_KEY") or os.getenv("OPENAI_API_KEY")


def get_structured_method() -> str:
    return (os.getenv("STRUCTURED_METHOD") or "").lower()


def get_model_default() -> str:
    """Fallback model name when the caller does not choose one."""
    return os.getenv("MODEL") or os.getenv("MODEL_NAME") or "gemini-2.0-flash"


def resolve_provider(model: str, provider: Optional[str] = None) -> str:
    """Provider for a given model name.

    `MODEL_PROVIDER_MAP` lets one dropdown mix providers, e.g.
      MODEL_PROVIDER_MAP=gemini-2.5-pro=google,qwen3.8-flash-next-iq2_xs=openai
    Names not listed fall back to LLM_PROVIDER.
    """
    if provider:
        return provider.lower()
    for pair in (os.getenv("MODEL_PROVIDER_MAP") or "").split(","):
        if "=" in pair:
            name, prov = pair.split("=", 1)
            if name.strip() == model.strip():
                return prov.strip().lower()
    return get_provider()


def get_llm(model: str, temperature: float, max_retries: int = 2, provider: Optional[str] = None):
    """Return a LangChain chat model for the configured provider."""
    model = model or get_model_default()
    provider = resolve_provider(model, provider)
    if os.getenv("LLM_DEBUG"):
        print(f"[llm] provider={provider} model={model}", flush=True)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            api_key=os.getenv("GEMINI_API_KEY"),
        )

    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_retries": max_retries,
        "api_key": get_api_key() or "not-needed",
    }
    base_url = get_base_url()
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def structured(llm, schema: type[BaseModel]):
    """Structured output wrapper; method 可开关（本地端点有时只支持 json_mode）."""
    method = get_structured_method()
    if method:
        return llm.with_structured_output(schema, method=method)
    return llm.with_structured_output(schema)


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort JSON extraction for endpoints that ignore structured-output."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else text
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None


def invoke_structured(llm, schema: type[BaseModel], prompt: str) -> BaseModel:
    """Structured call with a plain-text fallback for weak OpenAI-compatible endpoints.

    本地小模型经常不按 tool-calling 格式返回，这里退化为：直接生成文本 + 解析 JSON。
    """
    try:
        result = structured(llm, schema).invoke(prompt)
        if isinstance(result, BaseModel):
            return result
    except Exception:
        pass

    raw = llm.invoke(prompt)
    text = raw.content if isinstance(raw.content, str) else str(raw.content)
    data = _extract_json(text)
    if data is None:
        raise ValueError(f"结构化输出失败且无法从文本解析 JSON: {text[:200]}")
    return schema.model_validate(data)
