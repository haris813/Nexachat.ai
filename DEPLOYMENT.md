# Deployment guide

## 1. Production prerequisites

- HTTPS domain and reverse proxy/load balancer with SSE buffering disabled
- Python 3.12 container runtime
- PostgreSQL 16+, Redis 7+, and a private persistent volume mounted at `/app/data`
- A secret manager for all credentials
- An OpenRouter API key; optionally one live-search provider and a Meta WhatsApp business setup

Generate local secret values:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the first output as `SECRET_KEY` and the second as `ENCRYPTION_KEY`. Use unique values in every environment.

## 2. Provider credentials

### OpenRouter

Store the key only in the backend environment. For local development, the canonical file is the repository-root `.env`:

```env
AI_PROVIDER=openrouter
AI_DEMO_MODE=false
OPENROUTER_API_KEY=sk-or-v1-replace_with_real_key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/free
```

Restart every backend and worker process after changing `.env`. NexaChat never needs `OPENAI_API_KEY` when OpenRouter is selected. Demo AI is available only when explicitly enabled with `AI_DEMO_MODE=true`.

### Live search

Choose exactly one provider:

- Tavily: create a key in the [Tavily dashboard](https://app.tavily.com), then set `SEARCH_PROVIDER=tavily` and `TAVILY_API_KEY`. Its official [search endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/search) uses bearer authentication.
- Serper: create a key at [serper.dev](https://serper.dev), then set `SEARCH_PROVIDER=serper` and `SERPER_API_KEY`.
- Brave: create a subscription/key in the [Brave Search API dashboard](https://api-dashboard.search.brave.com/app/documentation), then set `SEARCH_PROVIDER=brave` and `BRAVE_SEARCH_API_KEY`.

Use `SEARCH_PROVIDER=demo` to disable live lookup safely. The application then refuses time-sensitive claims instead of returning mock “current” results.

### Meta WhatsApp Cloud API

Start with Meta’s [Cloud API getting-started guide](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/) and [webhook guide](https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/).

1. Create a Meta app with the WhatsApp product and connect a WhatsApp Business Account.
2. Record the business account id and sending phone-number id.
3. For production, create a system user and long-lived token with only the required WhatsApp permissions; do not rely on a short-lived dashboard test token.
4. Create random webhook verify and app-secret values.
5. Add the public callback `https://YOUR_DOMAIN/api/whatsapp/webhook`, enter `META_WHATSAPP_WEBHOOK_VERIFY_TOKEN`, and subscribe to message status events.
6. Configure:

```env
WHATSAPP_MODE=meta
META_WHATSAPP_ACCESS_TOKEN=...
META_WHATSAPP_PHONE_NUMBER_ID=...
META_WHATSAPP_BUSINESS_ACCOUNT_ID=...
META_WHATSAPP_WEBHOOK_VERIFY_TOKEN=...
META_APP_SECRET=...
META_GRAPH_API_VERSION=v23.0
```

`META_GRAPH_API_VERSION` is deliberately configurable; choose a version supported by your Meta app and upgrade it according to Meta’s version lifecycle. Validate first with a Meta test number. NexaChat sends only after the user reviews the exact recipient/content and confirms.

## 3. Required environment

```env
APP_URL=https://nexachat.example.com
SECRET_KEY=<unique random value>
ENCRYPTION_KEY=<Fernet key>
COOKIE_SECURE=true
AUTH_REQUIRED=true
DEMO_MODE=false

DATABASE_URL=postgresql+psycopg://user:password@host:5432/nexachat
REDIS_URL=redis://host:6379/0
UPLOAD_DIR=/app/data/uploads
ARTIFACT_DIR=/app/data/artifacts
```

Set reasonable limits for your capacity:

```env
MAX_UPLOAD_MB=25
MAX_EXTRACTED_CHARS=120000
FILE_RETENTION_HOURS=168
FILE_BACKGROUND_THRESHOLD_MB=8
RATE_LIMIT=120 per hour
WEB_REQUEST_TIMEOUT=15
ALLOW_PRIVATE_URLS=false
SENTRY_DSN=
SENTRY_TRACES_SAMPLE_RATE=0
```

Mount private persistent storage. For single-server deployments, local storage
is the default. For horizontally scaled or platform deployments, switch to S3:

```env
STORAGE_BACKEND=s3
S3_BUCKET=nexachat-artifacts
S3_PRESIGN_EXPIRY=3600
```

### AWS S3

```env
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=AKIA...
S3_SECRET_ACCESS_KEY=...
```

Create a private bucket with server-side encryption enabled, block all public
access, and attach an IAM policy limited to `s3:PutObject`, `s3:GetObject`,
`s3:DeleteObject`, and `s3:HeadObject` on the bucket ARN.

### Cloudflare R2

```env
S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_REGION=auto
```

### Railway Buckets

Railway injects bucket credentials as service variables. Reference them:

```env
S3_ENDPOINT=${{Bucket.BUCKET_ENDPOINT}}
S3_BUCKET=${{Bucket.BUCKET_NAME}}
S3_ACCESS_KEY_ID=${{Bucket.BUCKET_ACCESS_KEY_ID}}
S3_SECRET_ACCESS_KEY=${{Bucket.BUCKET_SECRET_ACCESS_KEY}}
S3_REGION=${{Bucket.BUCKET_REGION}}
```

Both the web service and worker must share the same bucket credentials so
generated artifacts are accessible from either process.

## 4. Compose deployment

```bash
cp .env.example .env
# edit .env and replace every production secret
docker compose pull
docker compose build
docker compose up -d
docker compose ps
```

The image runs `flask --app app.py db upgrade` before Gunicorn. The worker runs the same migration and then consumes the `nexachat` RQ queue. Compose retains `postgres_data`, `redis_data`, and `artifact_data`.

Before upgrades:

```bash
docker compose exec postgres pg_dump -U nexachat -d nexachat > nexachat-backup.sql
docker compose run --rm app flask --app app.py db upgrade
docker compose up -d --build
```

Test downgrade behavior in a disposable environment. The initial additive migration intentionally does not delete legacy tables on downgrade.

## 5. Generic platform deployment

Build the root `Dockerfile`, expose `PORT`, attach PostgreSQL/Redis/private storage, and use:

- Liveness: `/api/health`
- Readiness: `/api/ready`
- Metrics: `/metrics` on a private network
- Start command: the image default, or `flask --app app.py db upgrade && gunicorn ... wsgi:app`
- Worker command: `rq worker --url "$REDIS_URL" nexachat`

For Nginx:

```nginx
location / {
    proxy_pass http://nexachat:5000;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_read_timeout 180s;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;
}
```

The included `render.yaml` and `railway.json` are starting points. Confirm that the platform supports a writable persistent disk for both web and worker; ephemeral filesystems lose uploads/artifacts.

## 6. Release verification

Run before promotion:

```bash
ruff format --check .
ruff check .
mypy app
pytest --cov=app --cov-report=term-missing
bandit -q -r app
pip-audit -r requirements.txt
python -m compileall -q app tests app.py wsgi.py
node --check static/js/app.js
docker compose config
docker build -t nexachat-ai:release .
```

Smoke-test:

1. Register/login and confirm another browser cannot read the account’s resources.
2. Stream a direct chat.
3. Create and execute a live research plan; verify URLs and retrieval times.
4. Upload a CSV/PDF and generate/download artifacts.
5. Render one XLSX, PPTX, DOCX, and PDF artifact.
6. Record/transcribe audio and synthesize speech.
7. In `WHATSAPP_MODE=mock`, verify preparation does not send and confirm-send writes a mock provider id.
8. With a Meta test number, verify confirmation, send, and delivery webhook updates.
9. Confirm `/api/ready`, metrics, logs, backups, RQ worker health, retention, and alerting.

For a repeatable health-endpoint latency smoke test, run `python scripts/benchmark.py --base-url https://YOUR_DOMAIN --requests 50 --concurrency 5`.

## 7. Operations

- Back up PostgreSQL and `/app/data` together; artifact database rows and files must be restored consistently.
- Rotate provider keys independently. Rotate encryption through a decrypt/re-encrypt migration.
- Schedule `python -m scripts.cleanup_retention --apply` after first reviewing its dry-run output; it honors the configured retention window and preserves uploads referenced by WhatsApp audit rows.
- Alert on 5xx rate, provider errors, failed plans, RQ queue depth, disk usage, database connections, and WhatsApp delivery failures.
- Scale Gunicorn conservatively because SSE and Office generation occupy threads. Add worker processes after measuring memory and provider limits.
- Roll back the container image only after confirming its schema compatibility with the current database.
