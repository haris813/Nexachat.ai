from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DATA_DIR = BASE_DIR / "data"
ENV_PATH = BASE_DIR / ".env"

# Always resolve the backend environment from the repository root. This keeps
# Flask, python app.py, Gunicorn, and background workers independent of cwd.
load_dotenv(dotenv_path=ENV_PATH, override=False)

SUPPORTED_AI_PROVIDERS = {"openrouter", "openai", "ollama"}


class AIConfigurationError(RuntimeError):
    """Raised for safe, user-actionable AI provider configuration errors."""


def _env_value(name: str, default: str = "", environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    return str(source.get(name, default)).strip()


def resolve_ai_environment(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Resolve normalized provider settings without ever returning a secret value."""
    source = os.environ if environ is None else environ
    provider = _env_value("AI_PROVIDER", "openrouter", source).lower()
    demo_mode = _env_value("AI_DEMO_MODE", "false", source).lower() == "true"
    if demo_mode:
        provider = "demo"
    model = {
        "openrouter": _env_value("OPENROUTER_MODEL", "openrouter/free", source),
        "openai": _env_value("OPENAI_MODEL", "gpt-5-mini", source),
        "ollama": _env_value("OLLAMA_MODEL", "llama3.2", source),
        "demo": "demo",
    }.get(provider, "")
    configured = {
        "openrouter": bool(
            _env_value("OPENROUTER_API_KEY", environ=source)
            and _env_value("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1", source)
            and model
        ),
        "openai": bool(_env_value("OPENAI_API_KEY", environ=source) and model),
        "ollama": bool(_env_value("OLLAMA_BASE_URL", "http://localhost:11434", source) and model),
        "demo": demo_mode,
    }.get(provider, False)
    return {"provider": provider, "model": model, "configured": configured}


def ai_configuration_status(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return the public, secret-free configuration status for a Flask config."""
    provider = str(config.get("AI_PROVIDER", "openrouter")).strip().lower()
    demo_mode = bool(config.get("AI_DEMO_MODE", False))
    if demo_mode:
        provider = "demo"
    if provider == "openrouter":
        model = str(config.get("OPENROUTER_MODEL", "")).strip()
        configured = bool(
            str(config.get("OPENROUTER_API_KEY", "")).strip()
            and str(config.get("OPENROUTER_BASE_URL", "")).strip()
            and model
        )
    elif provider == "openai":
        model = str(config.get("OPENAI_MODEL", "")).strip()
        configured = bool(str(config.get("OPENAI_API_KEY", "")).strip() and model)
    elif provider == "ollama":
        model = str(config.get("OLLAMA_MODEL", "")).strip()
        configured = bool(str(config.get("OLLAMA_BASE_URL", "")).strip() and model)
    elif provider == "demo":
        model = "demo"
        configured = demo_mode
    else:
        model = ""
        configured = False
    return {"ai_provider": provider, "ai_model": model, "ai_configured": configured}


def validate_ai_configuration(
    config: Mapping[str, Any], *, require_credentials: bool = True
) -> dict[str, Any]:
    status = ai_configuration_status(config)
    provider = status["ai_provider"]
    if provider == "demo":
        if not bool(config.get("AI_DEMO_MODE", False)):
            raise AIConfigurationError("Demo mode must be enabled explicitly with AI_DEMO_MODE=true.")
        return status
    if provider not in SUPPORTED_AI_PROVIDERS:
        raise AIConfigurationError("Unsupported AI_PROVIDER. Use openrouter, openai, or ollama.")
    if require_credentials and not status["ai_configured"]:
        if provider == "openrouter":
            if not str(config.get("OPENROUTER_API_KEY", "")).strip():
                raise AIConfigurationError("OPENROUTER_API_KEY is missing from the backend environment.")
            if not str(config.get("OPENROUTER_BASE_URL", "")).strip():
                raise AIConfigurationError("OPENROUTER_BASE_URL is missing from the backend environment.")
            raise AIConfigurationError("OPENROUTER_MODEL is missing from the backend environment.")
        if provider == "openai":
            if not str(config.get("OPENAI_API_KEY", "")).strip():
                raise AIConfigurationError("OPENAI_API_KEY is missing from the backend environment.")
            raise AIConfigurationError("OPENAI_MODEL is missing from the backend environment.")
        if not str(config.get("OLLAMA_BASE_URL", "")).strip():
            raise AIConfigurationError("OLLAMA_BASE_URL is missing from the backend environment.")
        raise AIConfigurationError("OLLAMA_MODEL is missing from the backend environment.")
    return status


def _database_url() -> str:
    url = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DATA_DIR / 'nexachat.db'}"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SESSION_COOKIE_NAME = "nexachat_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    DATA_DIR = str(BASE_DATA_DIR)
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DATA_DIR / "uploads"))
    ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", str(BASE_DATA_DIR / "artifacts"))
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    AI_PROVIDER = _env_value("AI_PROVIDER", "openrouter").lower()
    AI_DEMO_MODE = _env_value("AI_DEMO_MODE", "false").lower() == "true"
    OPENAI_API_KEY = _env_value("OPENAI_API_KEY")
    OPENAI_MODEL = _env_value("OPENAI_MODEL", "gpt-5-mini")
    OPENAI_ALLOWED_MODELS = [
        item.strip()
        for item in os.getenv("OPENAI_ALLOWED_MODELS", "gpt-5-mini,gpt-5-nano,gpt-4.1-mini").split(",")
        if item.strip()
    ]
    OPENROUTER_API_KEY = _env_value("OPENROUTER_API_KEY")
    OPENROUTER_BASE_URL = _env_value("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    OPENROUTER_MODEL = _env_value("OPENROUTER_MODEL", "openrouter/free")
    OLLAMA_BASE_URL = _env_value("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = _env_value("OLLAMA_MODEL", "llama3.2")
    TRANSCRIPTION_MODEL = os.getenv("TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")
    TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
    TTS_VOICE = os.getenv("TTS_VOICE", "alloy")

    DEFAULT_SYSTEM_PROMPT = os.getenv(
        "DEFAULT_SYSTEM_PROMPT",
        "You are NexaChat, a helpful, accurate, and concise AI assistant. Use Markdown when it improves clarity.",
    )
    MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "30"))
    MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "12000"))
    MAX_SYSTEM_PROMPT_CHARS = int(os.getenv("MAX_SYSTEM_PROMPT_CHARS", "4000"))
    MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1400"))
    MAX_CONVERSATIONS_PER_SESSION = int(os.getenv("MAX_CONVERSATIONS_PER_SESSION", "100"))
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    MAX_EXTRACTED_CHARS = int(os.getenv("MAX_EXTRACTED_CHARS", "120000"))
    FILE_RETENTION_HOURS = int(os.getenv("FILE_RETENTION_HOURS", "168"))
    FILE_BACKGROUND_THRESHOLD_MB = int(os.getenv("FILE_BACKGROUND_THRESHOLD_MB", "8"))

    SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "demo").strip().lower()
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
    SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    WEB_REQUEST_TIMEOUT = int(os.getenv("WEB_REQUEST_TIMEOUT", "15"))
    ALLOW_PRIVATE_URLS = os.getenv("ALLOW_PRIVATE_URLS", "false").lower() == "true"

    WHATSAPP_MODE = os.getenv("WHATSAPP_MODE", "mock").strip().lower()
    META_WHATSAPP_ACCESS_TOKEN = os.getenv("META_WHATSAPP_ACCESS_TOKEN", "")
    META_WHATSAPP_PHONE_NUMBER_ID = os.getenv("META_WHATSAPP_PHONE_NUMBER_ID", "")
    META_WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("META_WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    META_WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("META_WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
    META_APP_SECRET = os.getenv("META_APP_SECRET", "")
    META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v23.0")

    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
    AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
    DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
    APP_URL = os.getenv("APP_URL", "http://localhost:5000")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5000")
    PORT = int(os.getenv("PORT", "5000"))
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    SENTRY_TRACES_SAMPLE_RATE = min(max(float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0")), 0), 1)
    REDIS_URL = os.getenv("REDIS_URL", "")
    RATELIMIT_STORAGE_URI = REDIS_URL or "memory://"
    RATELIMIT_DEFAULT = os.getenv("RATE_LIMIT", "120 per hour")
    RATELIMIT_HEADERS_ENABLED = True

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"
    DB_STARTUP_RETRIES = int(os.getenv("DB_STARTUP_RETRIES", "10"))
    DB_STARTUP_RETRY_DELAY = int(os.getenv("DB_STARTUP_RETRY_DELAY", "2"))

    # Storage backend: "local" (default) or "s3" (S3/R2/Railway Buckets)
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
    S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
    S3_BUCKET = os.getenv("S3_BUCKET", "")
    S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
    S3_REGION = os.getenv("S3_REGION", "us-east-1")
    S3_PRESIGN_EXPIRY = int(os.getenv("S3_PRESIGN_EXPIRY", "3600"))
    S3_PREFIX = os.getenv("S3_PREFIX", "")
