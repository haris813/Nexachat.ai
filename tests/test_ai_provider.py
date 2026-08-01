import json
from types import SimpleNamespace

import pytest

from app.config import (
    AIConfigurationError,
    resolve_ai_environment,
    validate_ai_configuration,
)
from app.services.ai import AIService


def test_openrouter_is_default_and_does_not_require_openai_key():
    status = resolve_ai_environment(
        {
            "OPENROUTER_API_KEY": "test-openrouter-key",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
            "OPENROUTER_MODEL": "openrouter/free",
            "OPENAI_API_KEY": "",
        }
    )
    assert status == {
        "provider": "openrouter",
        "model": "openrouter/free",
        "configured": True,
    }


def test_provider_name_is_normalized_case_insensitively():
    status = resolve_ai_environment(
        {
            "AI_PROVIDER": "  OpenRouter  ",
            "OPENROUTER_API_KEY": "test-openrouter-key",
        }
    )
    assert status["provider"] == "openrouter"
    assert status["configured"] is True


def test_missing_openrouter_key_is_a_configuration_error():
    with pytest.raises(AIConfigurationError, match="OPENROUTER_API_KEY is missing"):
        validate_ai_configuration(
            {
                "AI_PROVIDER": "openrouter",
                "AI_DEMO_MODE": False,
                "OPENROUTER_API_KEY": "",
                "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
                "OPENROUTER_MODEL": "openrouter/free",
            }
        )


def test_openai_requires_its_own_key():
    with pytest.raises(AIConfigurationError, match="OPENAI_API_KEY is missing"):
        validate_ai_configuration(
            {
                "AI_PROVIDER": "openai",
                "AI_DEMO_MODE": False,
                "OPENAI_API_KEY": "",
                "OPENAI_MODEL": "gpt-5-mini",
            }
        )


def test_ollama_does_not_require_a_cloud_key():
    status = validate_ai_configuration(
        {
            "AI_PROVIDER": "ollama",
            "AI_DEMO_MODE": False,
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "llama3.2",
        }
    )
    assert status["ai_configured"] is True


def test_invalid_provider_is_rejected():
    with pytest.raises(AIConfigurationError, match="Unsupported AI_PROVIDER"):
        validate_ai_configuration({"AI_PROVIDER": "unknown", "AI_DEMO_MODE": False})


def test_public_config_reports_safe_openrouter_status(client, app):
    app.config.update(
        AI_PROVIDER="openrouter",
        AI_DEMO_MODE=False,
        OPENROUTER_API_KEY="test-secret-that-must-not-leak",
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        OPENROUTER_MODEL="openrouter/free",
        OPENAI_API_KEY="",
    )
    payload = client.get("/api/config").get_json()
    assert payload["ai_provider"] == "openrouter"
    assert payload["ai_model"] == "openrouter/free"
    assert payload["ai_configured"] is True
    assert payload["default_model"] == "openrouter/free"
    assert "test-secret-that-must-not-leak" not in json.dumps(payload)
    assert "api_key" not in json.dumps(payload).lower()


def test_missing_openrouter_key_returns_error_event_not_demo(client, app):
    app.config.update(
        AI_PROVIDER="openrouter",
        AI_DEMO_MODE=False,
        OPENROUTER_API_KEY="",
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        OPENROUTER_MODEL="openrouter/free",
    )
    csrf = client.get("/api/config").get_json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    conversation = client.post("/api/conversations", json={}, headers=headers).get_json()
    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "hi", "model": "openrouter/free"},
        headers=headers,
        buffered=True,
    )
    body = response.get_data(as_text=True)
    assert "OPENROUTER_API_KEY is missing from the backend environment" in body
    assert "Demo mode is active" not in body


def test_configured_openrouter_streams_once_without_openai_key(app, monkeypatch):
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return iter(
                [
                    SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"))],
                        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1),
                    )
                ]
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    app.config.update(
        AI_PROVIDER="openrouter",
        AI_DEMO_MODE=False,
        OPENROUTER_API_KEY="test-openrouter-key",
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        OPENROUTER_MODEL="openrouter/free",
        OPENAI_API_KEY="",
    )
    monkeypatch.setattr(AIService, "_openrouter_client", lambda _self: fake_client)

    with app.app_context():
        generator = AIService().stream(
            [{"role": "user", "content": "hi"}],
            "You are helpful.",
            "openrouter/free",
        )
        events = []
        while True:
            try:
                events.append(next(generator))
            except StopIteration as stop:
                result = stop.value
                break

    assert len(calls) == 1
    assert calls[0]["model"] == "openrouter/free"
    assert events == [{"event": "delta", "data": {"text": "Hello"}}]
    assert result.provider == "openrouter"
    assert result.text == "Hello"
