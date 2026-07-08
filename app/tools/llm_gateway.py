"""LLM Gateway — 多 Provider + Failover 链。

按技术设计书 §7 实现：
- 读取 config/llm.yaml 配置
- 按 agent_model_map 为每个 Agent 分配 LLM
- 主 provider 失败自动切到 fallback_chain
- 支持 OpenAI 兼容协议（deepseek/openai/qwen/stepfun 都是兼容的）
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "llm.yaml",
)


def _load_config() -> dict[str, Any]:
    if not os.path.exists(_CONFIG_PATH):
        return {}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class LLMGateway:
    """LLM 网关 — 多 Provider + Failover。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or _load_config()
        self.providers: dict[str, dict] = self.config.get("providers", {})
        self.agent_map: dict[str, str] = self.config.get("agent_model_map", {})
        self.fallback_chain: list[str] = self.config.get(
            "fallback_chain", list(self.providers.keys())
        )
        self._clients: dict[str, httpx.AsyncClient] = {}
        for name, cfg in self.providers.items():
            api_key = os.environ.get(cfg.get("api_key_env", ""), "")
            self._clients[name] = httpx.AsyncClient(
                base_url=cfg.get("base_url", ""),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )

    async def aclose(self) -> None:
        for c in self._clients.values():
            await c.aclose()

    async def chat(
        self,
        agent_name: str,
        messages: list[dict[str, str]],
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        """调用 LLM。按 agent_map 选 provider，失败走 fallback_chain。

        Args:
            agent_name: Agent 名称（如 "phenotype_analyzer"）
            messages: OpenAI 格式消息列表
            json_mode: 是否强制 JSON 输出
            temperature: 覆盖配置的温度

        Returns:
            LLM 生成的文本

        Raises:
            RuntimeError: 所有 provider 都失败
        """
        primary = self.agent_map.get(agent_name, self.fallback_chain[0])
        chain = [primary] + [p for p in self.fallback_chain if p != primary]

        last_err: Exception | None = None
        for provider_name in chain:
            if provider_name not in self.providers:
                continue
            # 检查 API key 是否配置
            cfg = self.providers[provider_name]
            api_key = os.environ.get(cfg.get("api_key_env", ""), "")
            if not api_key:
                last_err = RuntimeError(f"{provider_name} 未配置 API key")
                continue
            try:
                return await self._call_provider(
                    provider_name, messages, json_mode, temperature
                )
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(
            f"所有 LLM provider 失败 (agent={agent_name}): {last_err}"
        )

    async def chat_json(
        self,
        agent_name: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> dict | list:
        """调用 LLM 并解析 JSON 输出。

        自动在 system prompt 追加 "请仅输出 JSON" 指令，
        并尝试从响应中提取 JSON（兼容 markdown 代码块包裹）。
        """
        msgs = list(messages)
        if msgs and msgs[0]["role"] == "system":
            msgs[0] = {
                "role": "system",
                "content": msgs[0]["content"] + "\n\n请仅输出纯 JSON，不要任何解释文字或 markdown 代码块。",
            }
        else:
            msgs.insert(0, {
                "role": "system",
                "content": "请仅输出纯 JSON，不要任何解释文字或 markdown 代码块。",
            })

        text = await self.chat(agent_name, msgs, json_mode=True, temperature=temperature)
        return _extract_json(text)

    async def _call_provider(
        self,
        name: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        temperature: float | None,
    ) -> str:
        cfg = self.providers[name]
        payload: dict[str, Any] = {
            "model": cfg.get("model", ""),
            "messages": messages,
            "max_tokens": cfg.get("max_tokens", 4096),
            "temperature": temperature if temperature is not None else cfg.get("temperature", 0.3),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        client = self._clients[name]
        resp = await client.post("/chat/completions", json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"{name} HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict | list:
    """从 LLM 响应中提取 JSON。

    兼容多种情况：
    - 纯 JSON
    - ```json ... ``` 代码块包裹
    - 混杂解释文字（取第一个 { 到最后一个 }）
    - 损坏/未闭合 JSON（尝试修复）
    """
    text = text.strip()
    if not text:
        return {}

    # 去除 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    import json
    import re

    def _try_parse(s: str):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    # 1. 直接尝试解析
    parsed = _try_parse(text)
    if isinstance(parsed, (dict, list)):
        return parsed

    # 2. 根据文本开头优先提取对象或数组
    def _extract_from_text(t: str):
        if t.startswith("["):
            # 优先尝试数组
            start = t.find("[")
            end = t.rfind("]")
            if start >= 0:
                if end > start:
                    candidate = t[start : end + 1]
                else:
                    candidate = t[start:]
                parsed = _try_parse(candidate)
                if isinstance(parsed, (dict, list)):
                    return parsed
                fixed = _repair_json(candidate)
                if fixed != candidate:
                    parsed = _try_parse(fixed)
                    if isinstance(parsed, (dict, list)):
                        return parsed

        # 尝试对象
        start = t.find("{")
        end = t.rfind("}")
        if start >= 0:
            if end > start:
                candidate = t[start : end + 1]
            else:
                candidate = t[start:]
            parsed = _try_parse(candidate)
            if isinstance(parsed, (dict, list)):
                return parsed
            fixed = re.sub(r'":\s*":', '"_key":', candidate)
            if fixed != candidate:
                parsed = _try_parse(fixed)
                if isinstance(parsed, (dict, list)):
                    return parsed
            fixed = _repair_json(candidate)
            if fixed != candidate:
                parsed = _try_parse(fixed)
                if isinstance(parsed, (dict, list)):
                    return parsed

        # 如果前面没返回，再尝试数组（作为 fallback）
        if not t.startswith("["):
            start = t.find("[")
            end = t.rfind("]")
            if start >= 0:
                if end > start:
                    candidate = t[start : end + 1]
                else:
                    candidate = t[start:]
                parsed = _try_parse(candidate)
                if isinstance(parsed, (dict, list)):
                    return parsed
                fixed = _repair_json(candidate)
                if fixed != candidate:
                    parsed = _try_parse(fixed)
                    if isinstance(parsed, (dict, list)):
                        return parsed

        return None

    result = _extract_from_text(text)
    if result is not None:
        return result

    raise ValueError(f"无法从 LLM 响应中提取 JSON: {text[:200]}")


def _repair_json(s: str) -> str:
    """尝试修复常见 JSON 格式问题。"""
    import re
    # 修复尾部多余的逗号（对象或数组）
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # 修复未转义的控制字符（保留换行和制表符，移除其他控制字符）
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    # 如果缺少闭合括号，尝试补全
    open_braces = s.count("{") - s.count("}")
    open_brackets = s.count("[") - s.count("]")
    if open_braces > 0:
        s += "}" * open_braces
    if open_brackets > 0:
        s += "]" * open_brackets
    return s
