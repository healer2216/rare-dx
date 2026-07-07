"""单 Agent 测试端点。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/agent")

_sessions: dict[str, dict] = {}


@router.post("/session")
async def create_session(user_message: str = "", safety_level: str = "strict"):
    import asyncio
    sid = f"s-{int(asyncio.get_event_loop().time() * 1000)}"
    _sessions[sid] = {
        "session_id": sid,
        "user_message": user_message,
        "safety_level": safety_level,
        "status": "created",
    }
    return {"session_id": sid, "status": "created"}


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        return {"error": "session not found"}
    return session


@router.post("/phenotype/{session_id}")
async def run_phenotype(session_id: str, text: str = ""):
    return {"session_id": session_id, "layer": "phenotype", "status": "stub", "vectors": []}


@router.post("/hypothesis/{session_id}")
async def run_hypothesis(session_id: str):
    return {"session_id": session_id, "layer": "hypothesis", "status": "stub", "hypotheses": []}


@router.post("/temporal/{session_id}")
async def run_temporal(session_id: str):
    return {"session_id": session_id, "layer": "temporal", "status": "stub", "temporal_matches": []}


@router.post("/genetic/{session_id}")
async def run_genetic(session_id: str, pedigree: dict | None = None):
    return {"session_id": session_id, "layer": "genetic", "status": "stub", "genetic_constraint": None}


@router.post("/pathway/{session_id}")
async def run_pathway(session_id: str):
    return {"session_id": session_id, "layer": "pathway", "status": "stub", "pathway": None}
