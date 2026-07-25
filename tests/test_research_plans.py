from __future__ import annotations

from datetime import UTC, datetime

from app.models import ResearchSource, TaskPlan, ToolRun
from app.services.research import SourceResult, WebResearchService


def test_research_plan_streams_citations_and_persists_sources(client, csrf_headers, app, monkeypatch):
    sources = [
        SourceResult(
            title="Official AI update",
            url="https://example.com/ai-update",
            snippet="A documented AI product update was published.",
            content="A documented AI product update was published with supporting detail.",
            retrieved_at=datetime.now(UTC),
        )
    ]
    monkeypatch.setattr(WebResearchService, "search", lambda self, query, **kwargs: sources)
    conversation = client.post("/api/conversations", json={}, headers=csrf_headers).get_json()
    planned = client.post(
        "/api/plans",
        json={
            "conversation_id": conversation["id"],
            "goal": "Search the web for the latest AI product news and provide sources.",
            "attachment_ids": [],
        },
        headers=csrf_headers,
    )
    assert planned.status_code == 201
    plan = planned.get_json()["plan"]
    assert plan["required_tools"] == ["web_search", "fetch_webpage"]
    execution = client.post(f"/api/plans/{plan['id']}/execute", json={}, headers=csrf_headers)
    body = execution.data.decode()
    assert execution.status_code == 200
    assert "event: progress" in body
    assert "event: done" in body
    assert "https://example.com/ai-update" in body
    assert "retrieved" in body

    with app.app_context():
        stored_plan = TaskPlan.query.one()
        assert stored_plan.status == "completed"
        assert ResearchSource.query.one().url == sources[0].url
        run = ToolRun.query.filter_by(tool_name="web_search").one()
        assert run.status == "completed"


def test_demo_research_fails_instead_of_inventing(client, csrf_headers):
    conversation = client.post("/api/conversations", json={}, headers=csrf_headers).get_json()
    planned = client.post(
        "/api/plans",
        json={
            "conversation_id": conversation["id"],
            "goal": "Search the latest market ranking and cite sources.",
            "attachment_ids": [],
        },
        headers=csrf_headers,
    ).get_json()["plan"]
    execution = client.post(f"/api/plans/{planned['id']}/execute", json={}, headers=csrf_headers)
    body = execution.data.decode()
    assert "event: error" in body
    assert "will not invent current facts" in body
