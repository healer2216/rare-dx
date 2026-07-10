"""SSE 流式诊断端点 — 异步直调 Agent + KnowS 证据检索。

按 PRD §8.1 SSE 事件类型协议实现：
  round_start / agent_start / agent_delta / agent_done
  phenotype_vector / hypothesis_ranking / temporal_match
  inheritance_pattern / evoi_recommendation / evidence
  report_delta / safety_valve / heartbeat / round_end / error

每层 Agent 调用 run_with_knows，真实检索证据并附在事件中。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from ..agents.phenotype_analyzer import run_with_knows as l1_run
from ..agents.hypothesis_generator import run_with_knows as l2_run
from ..agents.temporal_reasoner import run_with_knows as l3_run
from ..agents.genetic_reasoner import run_with_knows as l4_run
from ..agents.pathway_planner import run_with_knows as l5_run
from ..agents.report_synthesizer import run as l6_run
from ..agents.report_synthesizer import run_with_llm as l6_run_llm
from ..safety.guardrails import (
    check_safety,
    conservative_downgrade,
    escalate_safety_level,
)
from ..state.session import EvidencePool
from ..tools.knows_client import KnowsClient
from ..tools.llm_gateway import LLMGateway
from ..tools.report_export import generate_docx, generate_pdf
from ..storage import save_session, load_session, list_sessions, delete_session

router = APIRouter(prefix="/api")

_AGENT_LABEL = {
    "phenotype": "表型分析器",
    "hypothesis": "假设生成器",
    "temporal": "时序推理器",
    "genetic": "遗传推理器",
    "pathway": "路径规划器",
    "report": "报告综合器",
}

# 每层对应的 SSE 输出事件类型（PRD §8.1）
_LAYER_OUTPUT_EVENT = {
    "phenotype": "phenotype_vector",
    "hypothesis": "hypothesis_ranking",
    "temporal": "temporal_match",
    "genetic": "inheritance_pattern",
    "pathway": "evoi_recommendation",
    "report": "report_delta",
}


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


def _serialize(obj: Any) -> Any:
    """递归把 Pydantic 模型/枚举转成 JSON 安全结构。"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict") and not isinstance(obj, dict):
        try:
            return obj.dict()
        except Exception:
            pass
    if hasattr(obj, "value") and isinstance(obj, type(obj).__mro__[-1]):
        return obj.value
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


@router.get("/diagnostic/stream")
async def diagnostic_stream(
    user_message: str, session_id: str | None = None
) -> EventSourceResponse:
    print(f"[sse] diagnostic_stream start user_message={user_message[:80]}... session_id={session_id}", flush=True)
    sid = session_id or f"s-{int(asyncio.get_event_loop().time() * 1000)}"

    event_queue: asyncio.Queue = asyncio.Queue()

    async def push(event_type: str, data: dict) -> None:
        await event_queue.put({
            "event": event_type,
            "data": json.dumps(_serialize(data), ensure_ascii=False, default=str),
        })

    async def run_pipeline() -> None:
        """异步执行 5 层 + 报告，每层发 SSE 事件。"""
        knows = KnowsClient()
        llm_gw = LLMGateway()
        # 用 dict 累积 state（与同步 Agent 接口一致）
        state: dict = {
            "session_id": sid,
            "current_user_message": user_message,
            "current_backflow_iterations": 0,
        }
        evidence_pool: dict[str, Any] = {}

        # 层执行序列（含回流控制）
        # Layer 1/2/4/5/6 传 llm_gw 启用 LLM；其他层暂用纯规则
        async def call_layer(name: str, fn):
            if name in ("phenotype", "hypothesis", "genetic", "pathway"):
                return await fn(state, knows, llm_gw)
            return await fn(state, knows)

        layers = [
            ("phenotype", l1_run),
            ("hypothesis", l2_run),
            ("temporal", l3_run),
            ("genetic", l4_run),
            ("pathway", l5_run),
        ]

        try:
            print(f"[pipeline] session={sid} user_message={user_message[:80]}...", flush=True)
            await push("round_start", {"round": 1, "session_id": sid})

            # ===== 安全闸门 1：入口处高风险升级 =====
            safety_level = "standard"
            print(f"[pipeline] safety_level={safety_level} checking entry triggers...", flush=True)
            new_level, esc_trigger = escalate_safety_level(safety_level, user_message)
            if esc_trigger:
                safety_level = new_level
                state["safety_level"] = safety_level
                await push("safety_valve", {
                    "type": esc_trigger.valve_id,
                    "severity": esc_trigger.severity,
                    "message": esc_trigger.message,
                    "safety_level": safety_level,
                })

            # ===== 安全闸门 2：入口处全量检查（议题漂移/危急值/信息修订）=====
            entry_trigger = check_safety(state)
            if entry_trigger and entry_trigger.action == "refuse":
                await push("safety_valve", {
                    "type": entry_trigger.valve_id,
                    "severity": entry_trigger.severity,
                    "message": entry_trigger.message,
                    "action": "refuse",
                })
                await push("round_end", {"round": 1, "session_id": sid, "aborted": True})
                return

            pipeline_aborted = False

            for name, fn in layers:
                label = _AGENT_LABEL[name]
                print(f"[pipeline] layer={name} start state_keys={list(state.keys())[:10]}", flush=True)
                await push("agent_start", {"agent": name, "layer": name})
                await push("agent_delta", {"agent": name, "delta": f"{label} 推理中..."})

                try:
                    result = await call_layer(name, fn)
                except TypeError:
                    # report_synthesizer 是同步函数，回退
                    print(f"[pipeline] layer={name} fallback sync", flush=True)
                    result = fn(state)
                except Exception as e:
                    print(f"[pipeline] layer={name} failed: {e}", flush=True)
                    await push("error", {"code": "agent_failed", "message": f"{name}: {e}"})
                    pipeline_aborted = True
                    break

                print(f"[pipeline] layer={name} done keys={list(result.keys())[:8]}", flush=True)
                # Print layer-specific summaries
                if name == "phenotype":
                    pv = result.get("phenotype_profile")
                    if pv and hasattr(pv, "vectors"):
                        print(f"[pipeline] phenotype_vectors={len(pv.vectors)} llm_metrics={result.get('layer1_metrics')}", flush=True)
                elif name == "hypothesis":
                    hyps = result.get("hypotheses", [])
                    print(f"[pipeline] hypotheses={len(hyps)} top1={hyps[0].disease_name if hyps else None} top1_posterior={hyps[0].bayesian_score if hyps else None}", flush=True)
                elif name == "temporal":
                    tmatch = result.get("temporal_matches", [])
                    print(f"[pipeline] temporal_matches={len(tmatch)}", flush=True)
                elif name == "genetic":
                    patterns = result.get("inheritance_patterns", [])
                    print(f"[pipeline] inheritance_patterns={len(patterns)}", flush=True)
                elif name == "pathway":
                    steps = result.get("pathway_steps", [])
                    print(f"[pipeline] pathway_steps={len(steps)}", flush=True)
                state.update(result)

                # ===== 安全闸门 3：hypothesis 后保守降级 =====
                if name == "hypothesis":
                    state["safety_level"] = safety_level
                    should_down, reason = conservative_downgrade(state, safety_level)
                    if should_down and reason:
                        print(f"[pipeline] layer=hypothesis conservative_downgrade reason={reason}", flush=True)
                        await push("safety_valve", {
                            "type": "conservative_downgrade",
                            "severity": "warning",
                            "message": reason,
                            "action": "downgrade",
                        })
                        # 清空假设，阻止后续层基于低置信度假设推理
                        state["hypotheses"] = []
                        print(f"[pipeline] layer=hypothesis hypotheses cleared", flush=True)

                # ===== 安全闸门 4：每层后全量检查（跨层冲突/状态压缩）=====
                layer_trigger = check_safety(state)
                if layer_trigger and layer_trigger.valve_id not in ("topic_drift", "emergency"):
                    print(f"[pipeline] layer={name} safety_trigger={layer_trigger.valve_id}", flush=True)
                    await push("safety_valve", {
                        "type": layer_trigger.valve_id,
                        "severity": layer_trigger.severity,
                        "message": layer_trigger.message,
                        "action": layer_trigger.action,
                    })

                # 收集本层证据
                layer_evs = result.get("current_layer_evidences", [])
                print(f"[pipeline] layer={name} evidences={len(layer_evs)}", flush=True)
                if layer_evs:
                    for ev in layer_evs:
                        evidence_pool[ev.id] = ev
                    await push("evidence", {
                        "source_layer": name,
                        "references": [
                            {
                                "id": ev.id,
                                "title": ev.title,
                                "doi": ev.doi,
                                "journal": ev.journal,
                                "publish_date": ev.publish_date,
                                "study_type": ev.study_type,
                                "impact_factor": ev.impact_factor,
                                "abstract": (ev.abstract[:300] + "…") if ev.abstract and len(ev.abstract) > 300 else ev.abstract,
                                "grade": ev.grade.value if ev.grade else None,
                                "source": ev.source.value if ev.source else None,
                                "url": _build_evidence_url(ev),
                            }
                            for ev in layer_evs
                        ],
                    })

                # 输出事件
                output_event = _LAYER_OUTPUT_EVENT.get(name, "agent_done")
                output_payload = _build_layer_output(name, state)
                print(f"[pipeline] layer={name} push={output_event} keys={list(output_payload.keys())[:6]}", flush=True)
                await push(output_event, output_payload)
                await push("agent_done", {"agent": name, "output": output_payload})

                # 回流判定（genetic → hypothesis）
                if name == "genetic" and result.get("current_backflow_to_hypothesis"):
                    if state.get("current_backflow_iterations", 0) < 2:
                        state["current_backflow_iterations"] += 1
                        print(f"[pipeline] backflow genetic->hypothesis iteration={state['current_backflow_iterations']}", flush=True)
                        await push("safety_valve", {
                            "type": "cross_layer_conflict",
                            "message": "遗传推理与 Top-1 假设冲突，触发回流重评估",
                        })
                        # 重跑 L2-L4
                        for rname, rfn in [("hypothesis", l2_run), ("temporal", l3_run), ("genetic", l4_run)]:
                            await push("agent_start", {"agent": rname, "layer": rname})
                            try:
                                rstate = await rfn(state, knows)
                                state.update(rstate)
                                await push(_LAYER_OUTPUT_EVENT[rname], _build_layer_output(rname, state))
                            except Exception as e:
                                print(f"[pipeline] reflow layer={rname} failed: {e}", flush=True)
                                await push("error", {"code": "reflow_failed", "message": f"{rname}: {e}"})
                                break

                # 回流判定（pathway → phenotype）：演示剧本第1轮通常不触发
                if name == "pathway" and result.get("current_backflow_to_phenotype"):
                    if state.get("current_backflow_iterations", 0) < 2:
                        await push("safety_valve", {
                            "type": "info_revise",
                            "message": "推荐检查需要更详细表型信息，触发回流补充",
                        })

            # 报告（LLM 增强版）
            print("[pipeline] layer=report start", flush=True)
            if pipeline_aborted:
                await push("round_end", {"round": 1, "session_id": sid, "aborted": True})
                return
            await push("agent_start", {"agent": "report", "layer": "report"})
            await push("agent_delta", {"agent": "report", "delta": "综合推理结果生成报告..."})
            report_result = await l6_run_llm(state, llm_gw)
            state.update(report_result)
            report_data = report_result.get("report", {})
            print(f"[pipeline] layer=report done keys={list(report_data.keys())[:8]}", flush=True)
            await push("report_delta", report_data)
            await push("agent_done", {"agent": "report", "output": report_data})

            await push("round_end", {"round": 1, "session_id": sid})
        except Exception as e:
            await push("error", {"code": "pipeline_failed", "message": str(e)})
        finally:
            await knows.aclose()
            await llm_gw.aclose()
            # 持久化完整 state（含结构化数据），供下载端点生成排版精美的报告
            if isinstance(state, dict) and state.get("report"):
                save_session(sid, state.get("current_user_message", ""), state)

    async def event_generator() -> AsyncGenerator[dict, None]:
        pipeline_task = asyncio.create_task(run_pipeline())
        last_push = asyncio.get_event_loop().time()
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=5)
            except asyncio.TimeoutError:
                # 每隔 15 秒推送 heartbeat，防止 ModelScope 反向代理因空闲超时掐断 SSE
                now = asyncio.get_event_loop().time()
                if now - last_push >= 15:
                    last_push = now
                    yield {"event": "heartbeat", "data": json.dumps({"ts": int(now)})}
                continue
            last_push = asyncio.get_event_loop().time()
            yield event
            if event.get("event") in ("round_end", "error"):
                break
        await pipeline_task

    return EventSourceResponse(event_generator(), ping=None)


def _build_evidence_url(ev) -> str | None:
    """根据证据字段构造跳转 URL。

    优先级：DOI > source-specific > id。
    - DOI → https://doi.org/{doi}
    - paper_en 且 id 像 PMID → https://pubmed.ncbi.nlm.nih.gov/{id}
    - guide 且 id 含 ORPHA → https://www.orpha.net/consor/cgi-bin/OC_Exp.php?lng=EN&Expert={orpha}
    - 其他 → None（前端不显示跳转按钮）
    """
    if ev.doi:
        return f"https://doi.org/{ev.doi}"
    src = ev.source.value if ev.source else ""
    if src == "paper_en" and ev.id and ev.id.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{ev.id}/"
    if src == "guide" and ev.id:
        # ORPHA 号提取
        if "ORPHA" in ev.id or ev.id.isdigit():
            return f"https://www.orpha.net/consor/cgi-bin/OC_Exp.php?lng=EN&Expert={ev.id}"
    return None


def _build_layer_output(name: str, state: dict) -> dict:
    """从 state 提取对应层的输出 payload。"""
    if name == "phenotype":
        p = state.get("phenotype_profile")
        if not p:
            return {"phenotypes": []}
        payload = {
            "phenotypes": [
                {
                    "hpo_id": v.hpo_id,
                    "term_name": v.term_name,
                    "presence": v.presence if isinstance(v.presence, str) else v.presence.value,
                    "onset_age": v.onset_age,
                    "onset_age_unit": v.onset_age_unit,
                    "modifiers": [m.model_dump(exclude_none=True) for m in v.modifiers],
                }
                for v in p.vectors
            ]
        }
        metrics = state.get("layer1_metrics")
        if metrics:
            payload["metrics"] = metrics
        return payload
    if name == "hypothesis":
        return {
            "hypotheses": [
                {
                    "rank": h.rank,
                    "disease_id": h.disease_id,
                    "disease_name": h.disease_name,
                    "orpha_number": h.orpha_number,
                    "posterior_prob": h.bayesian_score,
                    "confidence": h.confidence,
                    "supporting_phenotypes": h.supporting_phenotypes,
                    "evidence_count": len(h.evidence_ids),
                    "reasoning_chain": h.reasoning_chain,
                }
                for h in state.get("hypotheses", [])
            ]
        }
    if name == "temporal":
        return {
            "matches": [
                {
                    "disease_id": tm.disease_id,
                    "overall_temporal_score": tm.overall_temporal_score,
                    "onset_consistency": tm.onset_consistency,
                    "progression_consistency": tm.progression_consistency,
                    "notes": tm.notes,
                }
                for tm in state.get("temporal_matches", [])
            ]
        }
    if name == "genetic":
        gc = state.get("genetic_constraint")
        if not gc:
            return {"pattern": "UNKNOWN", "confidence": 0.0, "compatible": [], "incompatible": []}
        return {
            "patterns": [
                {"mode": p.mode.value, "confidence": p.confidence, "evidence": p.supporting_evidence}
                for p in gc.inheritance_patterns
            ],
            "compatible": gc.compatible_diseases,
            "incompatible": gc.incompatible_diseases,
        }
    if name == "pathway":
        pw = state.get("diagnostic_pathway")
        if not pw:
            return {"steps": []}
        return {
            "steps": [
                {
                    "rank": s.rank,
                    "test_id": s.test_id,
                    "test_name": s.test_name,
                    "evoi_score": s.net_evoi,
                    "information_gain": s.information_gain,
                    "rationale": s.rationale,
                    "expected_outcomes": s.expected_outcomes,
                    "alternative_tests": s.alternative_tests,
                }
                for s in pw.steps
            ],
            "total_information_gain": pw.total_expected_information_gain,
        }
    return {}


@router.get("/report/download")
async def download_report(session_id: str, format: str = "docx"):
    """下载诊断报告（docx / pdf）。

    需要先用 SSE 端点 (diagnostic/stream) 完成一次诊断，系统按 session_id 缓存状态。
    """
    state = load_session(session_id)
    if not state:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=404,
            content={"error": "报告未找到", "message": "该 session_id 无缓存报告，请先完成一轮诊断"},
        )

    from fastapi.responses import Response

    if format == "pdf":
        content = generate_pdf(state, session_id)
        media_type = "application/pdf"
        filename = f"rare-dx-report-{session_id}.pdf"
    else:
        content = generate_docx(state, session_id)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"rare-dx-report-{session_id}.docx"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===== 会话管理端点 =====

@router.get("/sessions")
async def list_sessions_endpoint(limit: int = 20):
    """列出最近的诊断会话。"""
    return {"sessions": list_sessions(limit)}


@router.get("/sessions/{session_id}")
async def get_session_endpoint(session_id: str):
    """获取某会话的完整状态。"""
    state = load_session(session_id)
    if not state:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "会话未找到"})
    return {"session_id": session_id, "state": state}


@router.delete("/sessions/{session_id}")
async def delete_session_endpoint(session_id: str):
    """删除某会话及其审计日志。"""
    ok = delete_session(session_id)
    return {"deleted": ok, "session_id": session_id}


@router.get("/sessions/{session_id}/audit")
async def get_audit_endpoint(session_id: str):
    """获取某会话的完整审计日志。"""
    from ..storage import get_audit
    return {"session_id": session_id, "audit": get_audit(session_id)}
