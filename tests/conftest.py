import pytest

from app import create_app
from app.extensions import db


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    DATA_DIR = "/tmp"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AI_PROVIDER = "demo"
    OPENAI_API_KEY = ""
    OPENAI_MODEL = "gpt-5-mini"
    OPENAI_ALLOWED_MODELS = ["gpt-5-mini"]
    OLLAMA_BASE_URL = "http://localhost:11434"
    OLLAMA_MODEL = "llama3.2"
    DEFAULT_SYSTEM_PROMPT = "You are helpful."
    MAX_HISTORY_MESSAGES = 30
    MAX_INPUT_CHARS = 12000
    MAX_SYSTEM_PROMPT_CHARS = 4000
    MAX_OUTPUT_TOKENS = 300
    MAX_CONVERSATIONS_PER_SESSION = 100
    REDIS_URL = ""
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_DEFAULT = "1000 per hour"
    RATELIMIT_ENABLED = False
    LOG_LEVEL = "CRITICAL"
    METRICS_ENABLED = False
    DB_STARTUP_RETRIES = 1
    DB_STARTUP_RETRY_DELAY = 0


@pytest.fixture()
def app(tmp_path):
    TestConfig.DATA_DIR = str(tmp_path)
    TestConfig.UPLOAD_DIR = str(tmp_path / "uploads")
    TestConfig.ARTIFACT_DIR = str(tmp_path / "artifacts")
    TestConfig.MAX_UPLOAD_MB = 25
    TestConfig.MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    TestConfig.MAX_EXTRACTED_CHARS = 120000
    TestConfig.FILE_RETENTION_HOURS = 1
    TestConfig.FILE_BACKGROUND_THRESHOLD_MB = 8
    TestConfig.SEARCH_PROVIDER = "demo"
    TestConfig.SEARCH_MAX_RESULTS = 8
    TestConfig.WEB_REQUEST_TIMEOUT = 2
    TestConfig.ALLOW_PRIVATE_URLS = False
    TestConfig.WHATSAPP_MODE = "mock"
    TestConfig.ENCRYPTION_KEY = ""
    TestConfig.AUTH_REQUIRED = False
    TestConfig.DEMO_MODE = True
    TestConfig.TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
    TestConfig.TTS_MODEL = "tts-1"
    TestConfig.TTS_VOICE = "alloy"
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def csrf_headers(client):
    token = client.get("/api/config").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}
