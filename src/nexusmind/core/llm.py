"""LLM 网关（产品设计文档 Phase 2 架构层）：本地优先、三档可降级。

档位：
- ollama：本机 Ollama（默认 http://127.0.0.1:11434），数据不出境。
- openai：任何 OpenAI 兼容 API（用户自备 key，NEXUSMIND_LLM_API_KEY）。
- off：关闭；上层功能自动降级为规则/抽取式实现。

provider=auto（默认）：先探活 Ollama，活着用 ollama；否则有 key 用 openai；
都没有则 off。环境变量在调用时动态读取，便于托盘 Agent 热更新与测试。
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx


class LlmUnavailable(RuntimeError):
    """LLM 不可用（未配置/未启动/调用失败）时抛出，上层据此降级。"""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def provider_setting() -> str:
    return (_env("NEXUSMIND_LLM_PROVIDER", "auto") or "auto").lower()


def ollama_base() -> str:
    return _env("NEXUSMIND_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def openai_base() -> str:
    return _env("NEXUSMIND_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def model_name() -> str:
    return _env("NEXUSMIND_LLM_MODEL", "qwen2.5:7b")


def timeout_seconds() -> float:
    try:
        return float(_env("NEXUSMIND_LLM_TIMEOUT", "60") or 60)
    except ValueError:
        return 60.0


def _post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None,
               timeout: Optional[float] = None) -> Dict[str, Any]:
    """统一 JSON POST（测试可 monkeypatch 本函数模拟模型服务）。"""
    with httpx.Client(timeout=timeout or timeout_seconds()) as client:
        resp = client.post(url, json=payload, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


def _get_json(url: str, timeout: float = 2.0) -> Dict[str, Any]:
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def _ollama_alive() -> bool:
    try:
        _get_json(f"{ollama_base()}/api/tags", timeout=2.0)
        return True
    except Exception:
        return False


def resolve_provider() -> str:
    """返回实际生效的 provider：ollama | openai | off。"""
    setting = provider_setting()
    if setting == "off":
        return "off"
    if setting == "ollama":
        return "ollama" if _ollama_alive() else "off"
    if setting == "openai":
        return "openai" if _env("NEXUSMIND_LLM_API_KEY") else "off"
    # auto
    if _ollama_alive():
        return "ollama"
    if _env("NEXUSMIND_LLM_API_KEY"):
        return "openai"
    return "off"


def llm_status() -> Dict[str, Any]:
    provider = resolve_provider()
    return {
        "provider_setting": provider_setting(),
        "provider": provider,
        "available": provider != "off",
        "model": model_name(),
        "base_url": ollama_base() if provider == "ollama" else openai_base() if provider == "openai" else None,
        "hint": None if provider != "off" else (
            "未检测到可用 LLM：启动本地 Ollama（ollama serve 并拉取模型），"
            "或设置 NEXUSMIND_LLM_API_KEY 使用云端 API；未配置时 AI 功能自动降级为抽取式实现。"
        ),
    }


def _ollama_chat(messages: List[Dict[str, str]], temperature: float) -> str:
    data = _post_json(
        f"{ollama_base()}/api/chat",
        {"model": model_name(), "messages": messages, "stream": False,
         "options": {"temperature": temperature}},
    )
    message = data.get("message") or {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise LlmUnavailable("Ollama 返回空内容")
    return content


def _openai_chat(messages: List[Dict[str, str]], temperature: float) -> str:
    data = _post_json(
        f"{openai_base()}/chat/completions",
        {"model": model_name(), "messages": messages, "temperature": temperature},
        headers={"Authorization": f"Bearer {_env('NEXUSMIND_LLM_API_KEY')}"},
    )
    choices = data.get("choices") or []
    if not choices:
        raise LlmUnavailable("LLM API 未返回 choices")
    content = str((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise LlmUnavailable("LLM API 返回空内容")
    return content


def chat(messages: List[Dict[str, str]], *, temperature: float = 0.3) -> str:
    """多轮对话补全；不可用时抛 LlmUnavailable（上层必须降级，不许编造）。"""
    provider = resolve_provider()
    if provider == "off":
        raise LlmUnavailable("LLM 未配置或不可用")
    started = time.time()
    try:
        result = _ollama_chat(messages, temperature) if provider == "ollama" else _openai_chat(messages, temperature)
    except LlmUnavailable:
        raise
    except Exception as exc:
        raise LlmUnavailable(f"LLM 调用失败：{exc}") from exc
    _ = time.time() - started  # 耗时打点预留（后续可接入指标）
    return result


def generate(prompt: str, *, system: Optional[str] = None, temperature: float = 0.3) -> str:
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat(messages, temperature=temperature)
