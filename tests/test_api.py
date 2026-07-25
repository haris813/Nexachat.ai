from app.services.ai import AIService, StreamResult


def test_health_and_ready(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/ready").get_json()["database"] == "ok"


def test_csrf_is_required_for_mutations(client):
    assert client.post("/api/conversations", json={}).status_code == 403


def test_conversation_crud(client, csrf_headers):
    created = client.post("/api/conversations", json={"persona": "coding"}, headers=csrf_headers)
    assert created.status_code == 201
    conversation = created.get_json()
    assert conversation["title"] == "New conversation"
    assert conversation["persona"] == "coding"

    conversation_id = conversation["id"]
    renamed = client.patch(
        f"/api/conversations/{conversation_id}",
        json={"title": "API design", "is_pinned": True},
        headers=csrf_headers,
    )
    assert renamed.get_json()["title"] == "API design"
    assert renamed.get_json()["is_pinned"] is True

    fetched = client.get(f"/api/conversations/{conversation_id}").get_json()
    assert fetched["id"] == conversation_id

    assert client.delete(f"/api/conversations/{conversation_id}", headers=csrf_headers).status_code == 204
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_demo_stream_persists_messages(client, csrf_headers):
    conversation = client.post("/api/conversations", json={}, headers=csrf_headers).get_json()
    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "Explain Docker", "model": "gpt-5-mini"},
        headers=csrf_headers,
        buffered=True,
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "event: delta" in body
    assert "event: done" in body

    stored = client.get(f"/api/conversations/{conversation['id']}").get_json()
    assert [message["role"] for message in stored["messages"]] == ["user", "assistant"]
    assert "Demo mode" in stored["messages"][1]["content"]


def test_saved_memory_is_added_as_user_controlled_context(client, csrf_headers, monkeypatch):
    client.patch(
        "/api/preferences",
        json={"language": "hi", "memory": {"preferred_name": "Asha"}},
        headers=csrf_headers,
    )
    captured = {}

    def fake_stream(self, history, system_prompt, model):
        captured["prompt"] = system_prompt
        yield {"event": "delta", "data": {"text": "Namaste"}}
        return StreamResult(provider="demo", model=model, text="Namaste")

    monkeypatch.setattr(AIService, "stream", fake_stream)
    conversation = client.post("/api/conversations", json={}, headers=csrf_headers).get_json()
    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "Hello"},
        headers=csrf_headers,
        buffered=True,
    )
    assert response.status_code == 200
    assert '"preferred_name": "Asha"' in captured["prompt"]
    assert '"language": "hi"' in captured["prompt"]
    assert "user-controlled preferences" in captured["prompt"]


def test_rejects_empty_or_long_message(client, app, csrf_headers):
    conversation = client.post("/api/conversations", json={}, headers=csrf_headers).get_json()
    endpoint = f"/api/conversations/{conversation['id']}/messages"
    assert client.post(endpoint, json={"content": ""}, headers=csrf_headers).status_code == 400
    app.config["MAX_INPUT_CHARS"] = 3
    assert client.post(endpoint, json={"content": "four"}, headers=csrf_headers).status_code == 413


def test_anonymous_sessions_are_isolated(app):
    first = app.test_client()
    second = app.test_client()
    first_token = first.get("/api/config").get_json()["csrf_token"]

    created = first.post("/api/conversations", json={}, headers={"X-CSRF-Token": first_token}).get_json()
    assert len(first.get("/api/conversations").get_json()) == 1
    assert second.get("/api/conversations").get_json() == []
    assert second.get(f"/api/conversations/{created['id']}").status_code == 404


def test_regenerate_replaces_latest_assistant_message(client, csrf_headers):
    conversation = client.post("/api/conversations", json={}, headers=csrf_headers).get_json()
    endpoint = f"/api/conversations/{conversation['id']}/messages"
    client.post(
        endpoint,
        json={"content": "Hello", "model": "gpt-5-mini"},
        headers=csrf_headers,
        buffered=True,
    )
    before = client.get(f"/api/conversations/{conversation['id']}").get_json()
    first_assistant_id = before["messages"][-1]["id"]

    regenerated = client.post(
        f"/api/conversations/{conversation['id']}/regenerate",
        json={"model": "gpt-5-mini"},
        headers=csrf_headers,
        buffered=True,
    )
    assert regenerated.status_code == 200
    assert "event: done" in regenerated.get_data(as_text=True)

    after = client.get(f"/api/conversations/{conversation['id']}").get_json()
    assert [message["role"] for message in after["messages"]] == ["user", "assistant"]
    assert after["messages"][-1]["id"] != first_assistant_id


def test_duplicate_custom_instructions_and_stats(client, csrf_headers):
    conversation = client.post("/api/conversations", json={}, headers=csrf_headers).get_json()
    conversation_id = conversation["id"]
    updated = client.patch(
        f"/api/conversations/{conversation_id}",
        json={"system_prompt": "You are a strict API reviewer."},
        headers=csrf_headers,
    ).get_json()
    assert updated["persona"] == "custom"

    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Review this endpoint"},
        headers=csrf_headers,
        buffered=True,
    )
    duplicate = client.post(
        f"/api/conversations/{conversation_id}/duplicate",
        json={},
        headers=csrf_headers,
    )
    assert duplicate.status_code == 201
    assert duplicate.get_json()["message_count"] == 2

    stats = client.get("/api/stats").get_json()
    assert stats["conversations"] == 2
    assert stats["messages"] == 4
    assert stats["assistant_messages"] == 2
