"""工具封装层 — KnowS 检索 / 证据分级 / 疾病知识库。"""

from .knows_client import KnowsClient, LAYER_SOURCES
from .grade_evidence import (
    compute_evidence_strength,
    best_grade,
    format_citation,
)

__all__ = [
    "KnowsClient",
    "LAYER_SOURCES",
    "compute_evidence_strength",
    "best_grade",
    "format_citation",
]
