# Resume and interview guide

Use only claims you can demonstrate and explain.

## Project entry

**NexaChat AI — Multimodal AI Workspace**  
Python, Flask, OpenAI API, SQLAlchemy, PostgreSQL, Redis/RQ, JavaScript, Docker, Alembic, Prometheus, GitHub Actions

- Built a plan-first multimodal AI workspace with streaming chat, live cited research, secure file ingestion, voice transcription/synthesis, and validated Excel, PowerPoint, Word, PDF, and chart generation.
- Designed a schema-validated orchestration layer that persists plans, tool runs, source provenance, errors, and artifacts; added encrypted contacts and a Meta WhatsApp state machine that cannot send before exact user confirmation.
- Hardened a Flask/PostgreSQL/Redis deployment with owner-scoped authorization, CSRF, SSRF/upload defenses, migrations, non-root containers, observability, and automated test/type/security gates.

## LinkedIn project description

NexaChat AI is a multimodal productivity and automation workspace that turns natural-language requests into auditable plans. It combines streaming LLM chat, current web research with citations, secure document analysis, voice workflows, professional Office/PDF generation, and confirmed WhatsApp delivery. I built the provider boundaries, owner-scoped data model, task/tool audit trail, artifact validators, Redis jobs, migrations, observability, container stack, and automated security/quality gates. The project deliberately refuses unsupported current-data claims and places irreversible external actions behind deterministic server-side confirmation.

## 60-second interview explanation

“NexaChat starts as a normal streaming assistant, but complex requests are classified into a persisted task plan that the user approves. Every tool has a JSON Schema and a service boundary. Current-data requests must use a configured search adapter, and the sources and retrieval timestamps are stored with the result. Uploads are owner-scoped, signature-checked, extracted safely, and can become validated Excel, PowerPoint, Word, PDF, chart, or audio artifacts. Voice recordings can be reviewed and transcribed before use. WhatsApp is handled as a two-step state machine: prepare creates a pending audit row with the exact recipient and content, and only a separate one-time confirmation can invoke Meta. The stack runs on Flask, PostgreSQL, Redis/RQ, and Docker, with migrations, metrics, CI, dependency auditing, and isolation/security tests.”

## 3-minute technical explanation

The browser loads a server-rendered shell and gets a session-bound CSRF token plus public provider capabilities. A guest or registered user id becomes the ownership key for every top-level query. Simple messages use an SSE endpoint and the existing OpenAI/Ollama/demo abstraction. Time-sensitive language is intercepted so it cannot reach a non-research chat path.

Complex requests create a `TaskPlan` containing intent, ordered steps, required tools, attachments, expected output, and confirmation policy. Execution validates each tool input, persists a `ToolRun`, and streams status events. Search adapters retry transient failures, fetch only public HTTP(S) targets through SSRF validation, deduplicate sources, and wrap retrieved text as untrusted data. Structured model extraction is used only after evidence retrieval; demo mode refuses current claims.

Uploads live outside the public web root and pass size, extension, signature, Office ZIP, decompression, JSON/text, and ownership checks. Large extraction can move to Redis/RQ. Artifact generators consume structured data, escape spreadsheet formula prefixes, add source metadata, and reopen the result with the native Python library before marking it ready. The UI exposes preview/download/convert/regenerate actions.

Contacts use normalized phone numbers, authenticated encryption for recoverable fields, and keyed hashes for duplicate detection. WhatsApp prepare creates a `pending_confirmation` record and returns a one-time token. Confirm-send consumes that token, stamps `confirmed_at`, and only then calls the Meta adapter; the adapter independently rejects unconfirmed records. Signed webhook events update delivery status. Production uses PostgreSQL, Redis, a private volume, non-root containers, health/readiness/metrics endpoints, and CI checks for formatting, types, tests, security, dependencies, and the image build.

## Challenges solved

- Preserved a working legacy chat schema while adding user, plan, tool, file, artifact, source, contact, WhatsApp, preference, and usage models through an additive migration.
- Separated probabilistic model output from deterministic side-effect policy so a prompt cannot silently trigger messaging.
- Produced useful current-data deliverables without hard-coded rankings by requiring live evidence and structured extraction.
- Balanced a no-key demo with honest failure semantics: mock delivery is labeled and live facts are refused.
- Made generated Office files both useful and defensible through formatting, formula escaping, source metadata, structural reopening, tests, and render QA.

## Decisions to explain

### Why SSE instead of WebSockets?

Chat tokens and task progress primarily flow server-to-client. SSE works over normal HTTP, is easy to proxy and inspect, supports event types, and avoids the state/operational cost of a bidirectional socket. REST still performs cancellation and confirmation.

### How are hallucinated current facts prevented?

The direct chat endpoint detects current-data terms and returns `requires_plan`. The research plan requires a configured Tavily, Serper, or Brave adapter. Demo search throws a safe refusal. URLs, snippets, and retrieval timestamps are stored and rendered as citations.

### What is the prompt-injection strategy?

Retrieved and uploaded content is treated as untrusted data, wrapped in explicit delimiters, and never used as system instructions. Tools are server-selected, schema-validated, and constrained; URL fetches enforce SSRF controls. This reduces risk but does not claim to eliminate prompt injection.

### How is tenant isolation enforced?

A session maps to a guest or registered `User`. Every top-level resource stores `owner_id`, helper queries filter by it, nested resources are reached through owned parents, and download/send routes repeat the ownership check. Tests use two clients to verify isolation.

### Why encrypt contacts and also hash phone numbers?

Fernet supplies confidentiality and integrity for values that must later be sent. A keyed HMAC of the normalized number provides deterministic duplicate detection without a plaintext search column.

### How is accidental WhatsApp delivery prevented?

Prepare writes `pending_confirmation` and returns a short-lived one-time token plus masked recipient/exact body. Confirm-send consumes the token, sets `confirmed_at`, then calls the provider. The provider method independently rejects unconfirmed rows. Mock mode records a non-delivery provider id for demos.

### How are generated files validated?

Generators accept structured inputs. XLSX strings are formula-escaped, Office/PDF files include source metadata, and each output is reopened with openpyxl/python-pptx/python-docx/pypdf. Tests assert structural expectations; release QA renders visual formats.

### How would you scale it?

Use PostgreSQL and Redis, multiple bounded Gunicorn instances behind an SSE-aware proxy, separate RQ workers, managed secrets, and a shared private storage adapter. The current local-volume backend must be replaced before uncoordinated horizontal replicas.

## Honest limitations

- Storage is local/private-volume based, not S3.
- Plan execution streams from the web process; only large extraction is queued.
- PPTX generation does not write native speaker-note XML.
- Authentication is local email/password, not OAuth/SSO.
- Cost reporting is instrumentation-ready but only populated when usage events provide estimates.

## ATS keywords

Python, Flask, JavaScript, OpenAI Responses API, LLM orchestration, tool calling, JSON Schema, prompt-injection defense, retrieval-augmented generation, web research, Server-Sent Events, SQLAlchemy, Alembic, PostgreSQL, Redis, RQ, REST API, multimodal AI, speech-to-text, text-to-speech, openpyxl, python-pptx, python-docx, ReportLab, Meta WhatsApp Cloud API, encryption, CSRF, SSRF, authorization, rate limiting, Docker, Gunicorn, Prometheus, Grafana, GitHub Actions, pytest, mypy, Ruff, Bandit, dependency auditing, CI/CD.

## Demo checkpoints

1. Show a direct streaming chat and conversation archive/pin/search.
2. Run a live research + Excel plan and inspect source links and workbook metadata.
3. Upload a CSV, generate a chart and presentation, then open the files.
4. Record, transcribe, edit, and reuse a voice note.
5. Prepare a WhatsApp draft and pause at the confirmation dialog; use mock mode for a safe portfolio demo.
6. Show tests, CI workflow, migration, tool schemas, and security controls in code.

## Likely interview follow-ups

- How do database transactions behave if one CSV contact row is invalid? Each row uses a savepoint so valid rows survive.
- What prevents spreadsheet formula injection? Text beginning with formula control characters is prefixed as literal content.
- What happens if a search result redirects to localhost? Every redirect target is resolved and revalidated.
- Can users download someone else’s artifact by guessing a UUID? No; the lookup filters by both id and owner.
- What happens when Redis is unavailable? Small files extract synchronously and local development rate limiting can use memory; production should alert/fail health policy appropriately.
- Why not let the model call Meta directly? Irreversible actions need a deterministic server-side confirmation policy outside probabilistic model output.
