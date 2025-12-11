import pytest
import httpx
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.main import app


@pytest.mark.asyncio
async def test_math_tool_success():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/run-task",
            json={"goal": "2+2", "tools": ["math"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["output"]["result"] == 4.0
    assert body["trace"][0]["tool"] == "math"


@pytest.mark.asyncio
async def test_governance_note_and_fetch():
    proposal_id = "TEST-123"
    goal = f"Add governance note to proposal {proposal_id} about testing"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        run_resp = await client.post(
            "/run-task",
            json={"goal": goal, "tools": ["governance_note"]},
        )
        assert run_resp.status_code == 200
        run_body = run_resp.json()
        assert run_body["trace"][0]["status"] == "success"

        fetch_resp = await client.get(f"/governance-notes/{proposal_id}")
        assert fetch_resp.status_code == 200
        notes = fetch_resp.json()["notes"]
        assert any("testing" in note["note"] for note in notes)


@pytest.mark.asyncio
async def test_web_search_mock():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/run-task",
            json={"goal": "Latest AI news", "tools": ["web_search"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("success", "partial")
    assert body["trace"][0]["tool"] == "web_search"
    assert "results" in body["trace"][0]["output"]
