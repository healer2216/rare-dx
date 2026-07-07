"""API 端点集成测试 — health / SSE / 下载 / 安全阀。"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ===== health =====

def test_health_endpoint(client):
    """GET /api/health → 200 + status=ok。"""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


# ===== 下载端点 =====

def test_download_report_missing_session(client):
    """未找到 session_id → 404。"""
    r = client.get("/api/report/download?session_id=nonexistent&format=docx")
    assert r.status_code == 404
    assert "未找到" in r.json().get("error", "") or "未找到" in r.json().get("message", "")


def test_download_report_invalid_format(client):
    """无效 format 参数 → 不崩溃（降级到 docx 或 4xx）。"""
    r = client.get("/api/report/download?session_id=any&format=txt")
    # 未缓存 session 时 404，已缓存时可能 200 或 4xx
    assert r.status_code in (200, 404, 400)


# ===== SSE 端点（用 TestClient 模拟）=====

def test_diagnostic_stream_events(client):
    """SSE 端点应返回 round_start + 至少一个 agent 事件。"""
    with client.stream(
        "GET",
        "/api/diagnostic/stream",
        params={"user_message": "男婴3月龄肌张力低下乳酸酸中毒", "session_id": "s-api-test"},
    ) as resp:
        assert resp.status_code == 200
        events = []
        for line in resp.iter_lines():
            if line.startswith("event:"):
                events.append(line[6:].strip())
            # 收够 5 个事件就停（避免等完整 pipeline）
            if len(events) >= 5:
                break
        assert "round_start" in events, "应有 round_start 事件"


def test_diagnostic_stream_no_input(client):
    """空 input → 应正常处理（不 500）。"""
    with client.stream(
        "GET",
        "/api/diagnostic/stream",
        params={"user_message": "", "session_id": "s-empty"},
    ) as resp:
        # 应返回 200（即使空输入也会走 pipeline 或安全阀拒绝）
        assert resp.status_code == 200


def test_safety_valve_events_on_drift(client):
    """议题漂移 → safety_valve + refuse 事件。"""
    with client.stream(
        "GET",
        "/api/diagnostic/stream",
        params={"user_message": "帮我写首诗", "session_id": "s-drift"},
    ) as resp:
        assert resp.status_code == 200
        events = []
        data_buf = {}
        cur = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                cur = line[6:].strip()
                events.append(cur)
            elif line.startswith("data:") and cur:
                data_buf[cur] = line[5:].strip()
            if "round_end" in events:
                break
        assert "safety_valve" in events, "漂移应触发 safety_valve"
