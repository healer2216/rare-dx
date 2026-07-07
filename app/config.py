"""配置加载 — YAML + 环境变量。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_yaml(name: str) -> dict[str, Any]:
    path = _CONFIG_DIR / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_llm_config() -> dict[str, Any]:
    return _load_yaml("llm.yaml")


def get_reasoning_config() -> dict[str, Any]:
    return _load_yaml("reasoning.yaml")


def get_disease_kb_config() -> dict[str, Any]:
    return _load_yaml("disease_kb.yaml")


def get_knows_api_key() -> str | None:
    return os.environ.get("KNOWS_API_KEY")


def get_knows_base_url() -> str:
    return os.environ.get("KNOWS_BASE_URL", "https://api.nullht.com/v1")


def get_safety_level() -> str:
    return os.environ.get("SAFETY_LEVEL", "strict")
