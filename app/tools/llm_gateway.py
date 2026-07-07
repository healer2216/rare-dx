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

    兼容三种情况：
    - 纯 JSON
    - ```json ... ``` 代码块包裹
    - 混杂解释文字（取第一个 { 到最后一个 }）
    """
    text = text.strip()
    # 去除 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首尾 ``` 行
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # 直接尝试解析
    import json
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 提取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # 容错：flash 小模型可能损坏 JSON key（如 "impression":"..." → ": ":"..."）
        # 尝试修复损坏的 key（key 为空串或含非字母数字的损坏模式）
        import re
        # 把 ": ": 或 ": ":"  这种损坏 key（冒号前后无有效键名）替换为 _key 占位
        fixed = re.sub(r'":\s*":', '"_key":', candidate)
        if fixed != candidate:
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
    # 提取数组
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法从 LLM 响应中提取 JSON: {text[:200]}")
