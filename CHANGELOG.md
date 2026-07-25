# Changelog

## 2.0.0 - 2026-07-24

- Rebuilt the product as a plan-first multimodal AI workspace.
- Added schema-validated tools, persisted task plans/runs, progress SSE, cancellation, and analytics.
- Added Tavily, Serper, and Brave research adapters with citations, safe fetching, and current-data refusal.
- Added secure multimodal uploads, extraction, Redis/RQ large-file jobs, and retention metadata.
- Added professional XLSX, PPTX, DOCX, PDF, PNG chart, audio, and Markdown artifact pipelines with validation.
- Added browser voice recording, transcription, editable transcripts, and speech synthesis.
- Added encrypted contacts, CSV import, and confirmed Meta WhatsApp text/audio delivery with webhooks and mock mode.
- Added user accounts, guest isolation, explicit memory/preferences, archive state, and a polished responsive three-pane UI.
- Added additive Alembic migrations, container worker/storage support, expanded tests, type/security checks, and CI.
- Rewrote architecture, API, deployment, security, demo, contribution, and portfolio documentation.

## 1.1.0

- Added CSRF protection for state-changing API calls.
- Added conversation search, pinning, and duplication.
- Added per-conversation custom system instructions.
- Added a Product Engineer persona.
- Added workspace analytics for chats, messages, tokens, latency, and providers.
- Added custom Prometheus AI metrics and a provisioned Grafana dashboard.
- Hardened the Docker Compose application container with a read-only filesystem, no-new-privileges, and dropped capabilities.
- Expanded API, architecture, deployment, resume, and interview documentation.

## 1.0.0

- Initial production-ready portfolio release with SSE streaming, persistent chats, OpenAI/Ollama/demo providers, PostgreSQL, Redis, Docker, tests, CI, health checks, metrics, and cloud deployment files.
