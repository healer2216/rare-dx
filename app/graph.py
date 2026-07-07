"""LangGraph 状态机 · 6 节点 + 条件边 + 回流。"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "checkpoints.db"
CHECKPOINT_DB_PATH = os.environ.get("RARE_DX_CHECKPOINT_DB", str(_DEFAULT_DB))


def phenotype_node(state: Any) -> dict:
    from .agents.phenotype_analyzer import run
    return run(state)


def hypothesis_node(state: Any) -> dict:
    from .agents.hypothesis_generator import run
    return run(state)


def temporal_node(state: Any) -> dict:
    from .agents.temporal_reasoner import run
    return run(state)


def genetic_node(state: Any) -> dict:
    from .agents.genetic_reasoner import run
    return run(state)


def pathway_node(state: Any) -> dict:
    from .agents.pathway_planner import run
    return run(state)


def report_node(state: Any) -> dict:
    from .agents.report_synthesizer import run
    return run(state)


def route_after_genetic(state: Any) -> str:
    if state.get("current_backflow_to_hypothesis"):
        return "hypothesis"
    return "pathway"


def route_after_pathway(state: Any) -> str:
    if state.get("current_backflow_to_phenotype"):
        return "phenotype"
    return "report"


def build_graph() -> Any:
    from .state.session import DiagnosticSession

    graph = StateGraph(DiagnosticSession)
    graph.add_node("phenotype", phenotype_node)
    graph.add_node("hypothesis", hypothesis_node)
    graph.add_node("temporal", temporal_node)
    graph.add_node("genetic", genetic_node)
    graph.add_node("pathway", pathway_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "phenotype")
    graph.add_edge("phenotype", "hypothesis")
    graph.add_edge("hypothesis", "temporal")
    graph.add_edge("temporal", "genetic")
    graph.add_conditional_edges("genetic", route_after_genetic, {
        "hypothesis": "hypothesis",
        "pathway": "pathway",
    })
    graph.add_conditional_edges("pathway", route_after_pathway, {
        "phenotype": "phenotype",
        "report": "report",
    })
    graph.add_edge("report", END)

    return graph.compile()


_saver_lock = threading.Lock()
_saver_instance: Any = None


def get_saver() -> Any:
    global _saver_instance
    if _saver_instance is not None:
        return _saver_instance
    with _saver_lock:
        if _saver_instance is not None:
            return _saver_instance
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        _saver_instance = saver
    return _saver_instance


def build_graph_with_checkpoint(checkpointer: Any | None = None) -> Any:
    if checkpointer is None:
        checkpointer = get_saver()
    from .state.session import DiagnosticSession

    graph = StateGraph(DiagnosticSession)
    graph.add_node("phenotype", phenotype_node)
    graph.add_node("hypothesis", hypothesis_node)
    graph.add_node("temporal", temporal_node)
    graph.add_node("genetic", genetic_node)
    graph.add_node("pathway", pathway_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "phenotype")
    graph.add_edge("phenotype", "hypothesis")
    graph.add_edge("hypothesis", "temporal")
    graph.add_edge("temporal", "genetic")
    graph.add_conditional_edges("genetic", route_after_genetic, {
        "hypothesis": "hypothesis",
        "pathway": "pathway",
    })
    graph.add_conditional_edges("pathway", route_after_pathway, {
        "phenotype": "phenotype",
        "report": "report",
    })
    graph.add_edge("report", END)

    return graph.compile(checkpointer=checkpointer)
