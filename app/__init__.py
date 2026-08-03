from __future__ import annotations

import logging
import secrets
import time
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, request, session
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

from .config import Config, validate_ai_configuration
from .extensions import db, limiter, metrics, migrate
from .models import User
from .routes.api import api_bp
from .routes.web import web_bp
from .routes.workspace import workspace_bp
from .services.storage import init_storage


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent.parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent.parent / "static"),
    )
    app.config.from_object(Config)
    if config_object is not Config:
        app.config.from_object(config_object)
    configure_logging(app)
    ai_status = validate_ai_configuration(app.config, require_credentials=False)
    app.config["AI_PROVIDER"] = ai_status["ai_provider"]
    app.logger.info("AI provider: %s", ai_status["ai_provider"])
    app.logger.info("AI model: %s", ai_status["ai_model"])
    app.logger.info("AI configured: %s", "yes" if ai_status["ai_configured"] else "no")
    if ai_status["ai_provider"] == "openrouter":
        app.logger.info("OpenRouter base URL: %s", app.config["OPENROUTER_BASE_URL"])
    if app.config.get("SENTRY_DSN"):
        import sentry_sdk

        sentry_sdk.init(
            dsn=app.config["SENTRY_DSN"],
            traces_sample_rate=app.config["SENTRY_TRACES_SAMPLE_RATE"],
            send_default_pii=False,
        )

    for path_key in ("DATA_DIR", "UPLOAD_DIR", "ARTIFACT_DIR"):
        Path(app.config[path_key]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    if app.config.get("METRICS_ENABLED", True):
        metrics.init_app(app)

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(workspace_bp, url_prefix="/api")

    @app.get("/health")
    @limiter.exempt
    def root_health():
        """Keep the platform health check independent of request rate limits."""
        return jsonify({"status": "ok", "service": "nexachat-ai"})

    register_request_hooks(app)
    register_error_handlers(app)

    with app.app_context():
        initialize_database(app)
        init_storage(app)

    return app


def configure_logging(app: Flask) -> None:
    level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def register_request_hooks(app: Flask) -> None:
    @app.before_request
    def attach_request_context() -> None:
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        if "user_id" not in session:
            session["user_id"] = str(uuid.uuid4())
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        user = db.session.get(User, session["user_id"])
        if user is None:
            user = User(id=session["user_id"], is_guest=True, display_name="Demo workspace")
            db.session.add(user)
            db.session.commit()
        g.started_at = time.perf_counter()

    @app.after_request
    def add_response_headers(response):
        response.headers["X-Request-ID"] = g.get("request_id", "unknown")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; connect-src 'self'; img-src 'self' data:; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'"
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elapsed = time.perf_counter() - g.get("started_at", time.perf_counter())
        app.logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            request.path,
            response.status_code,
            elapsed * 1000,
            g.get("request_id"),
        )
        return response


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found", "request_id": g.get("request_id")}), 404
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>404 — NexaChat AI</title>"
            "<style>"
            "body{margin:0;min-height:100vh;display:grid;place-items:center;"
            "background:#080b11;color:#f4f6fb;font-family:Inter,system-ui,sans-serif;text-align:center}"
            "h1{font-size:4rem;margin:0;background:linear-gradient(145deg,#806cff,#4f8cff);"
            "-webkit-background-clip:text;-webkit-text-fill-color:transparent}"
            "p{color:#9aa4b5;margin:1rem 0 2rem}"
            "a{display:inline-block;padding:.75rem 1.5rem;background:linear-gradient(145deg,#806cff,#4f8cff);"
            "color:#fff;text-decoration:none;border-radius:10px;font-weight:600;font-size:.875rem}"
            "a:hover{filter:brightness(1.1)}"
            "</style></head><body>"
            "<div><h1>404</h1><p>This page doesn't exist.</p>"
            '<a href="/">Back to NexaChat AI</a></div>'
            "</body></html>",
            404,
        )

    @app.errorhandler(429)
    def rate_limited(_error):
        return jsonify({"error": "Too many requests. Please wait and try again."}), 429

    @app.errorhandler(Exception)
    def unhandled(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unhandled error request_id=%s", g.get("request_id"))
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error", "request_id": g.get("request_id")}), 500
        return "Internal server error", 500


def initialize_database(app: Flask) -> None:
    retries = app.config.get("DB_STARTUP_RETRIES", 10)
    delay = app.config.get("DB_STARTUP_RETRY_DELAY", 2)
    for attempt in range(1, retries + 1):
        try:
            db.session.execute(text("SELECT 1"))
            db.create_all()
            app.logger.info("Database ready")
            return
        except Exception:
            db.session.rollback()
            if attempt == retries:
                raise
            app.logger.warning("Database unavailable; retrying (%s/%s)", attempt, retries)
            time.sleep(delay)
