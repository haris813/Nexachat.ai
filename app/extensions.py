from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from prometheus_client import Counter, Histogram
from prometheus_flask_exporter import PrometheusMetrics

db = SQLAlchemy()
migrate = Migrate(compare_type=True)
limiter = Limiter(key_func=get_remote_address)
metrics = PrometheusMetrics.for_app_factory()

ai_requests_total = Counter(
    "nexachat_ai_requests_total",
    "Completed AI responses",
    ["provider", "model", "status"],
)
ai_response_latency_seconds = Histogram(
    "nexachat_ai_response_latency_seconds",
    "End-to-end AI response latency",
    ["provider", "model"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 180),
)
ai_tokens_total = Counter(
    "nexachat_ai_tokens_total",
    "AI tokens processed",
    ["provider", "model", "direction"],
)
tool_runs_total = Counter(
    "nexachat_tool_runs_total",
    "Completed tool executions",
    ["tool", "status"],
)
tool_latency_seconds = Histogram(
    "nexachat_tool_latency_seconds",
    "Tool execution latency",
    ["tool"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
