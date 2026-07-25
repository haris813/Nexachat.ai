from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DATA_DIR = BASE_DIR / "data"


def _database_url() -> str:
    url = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DATA_DIR / 'nexachat.db'}"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _ai_provider() -> str:
    configured = os.getenv("AI_PROVIDER", "").strip().lower()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if configured == "openai":
        return "openai" if api_key else "demo"
    if configured in {"ollama", "demo"}:
        return configured
    return "openai" if api_key else "demo"


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

    AI_PROVIDER = _ai_provider()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    OPENAI_ALLOWED_MODELS = [
        item.strip()
        for item in os.getenv("OPENAI_ALLOWED_MODELS", "gpt-5-mini,gpt-5-nano,gpt-4.1-mini").split(",")
        if item.strip()
    ]
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
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

