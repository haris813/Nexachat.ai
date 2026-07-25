# Contributing

## Local setup

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
flask --app app.py db upgrade
python app.py
```

Keep `AI_PROVIDER=demo`, `SEARCH_PROVIDER=demo`, and `WHATSAPP_MODE=mock` for credential-free development.

## Before opening a change

```powershell
ruff format .
ruff check .
mypy app
pytest --cov=app --cov-report=term-missing
bandit -q -r app
pip-audit -r requirements.txt
python -m compileall -q app tests app.py wsgi.py
node --check static/js/app.js
```

Add tests for successful behavior, ownership isolation, invalid input, and unsafe side effects. Artifact changes must reopen the native format and, where layout matters, render it for visual review.

## Engineering conventions

- Route handlers validate HTTP concerns and delegate provider/file/artifact behavior to services.
- Every persisted resource includes an owner or is reached through an owned parent.
- External facts require a configured live provider and stored citations.
- Never put provider keys, local paths, tracebacks, or decrypted contact data in client responses.
- Add JSON Schema before exposing a new tool; mark side-effecting tools explicitly.
- External actions require a distinct prepare/confirm execution boundary and an audit record.
- Use additive Alembic migrations and preserve existing user data.
- Keep demo behavior deterministic and clearly labeled; it must not imitate current facts or successful real delivery.
- Update `API.md`, `docs/openapi.yaml`, the Postman collection, and `.env.example` with contract/config changes.

## Database changes

```powershell
flask --app app.py db migrate -m "describe the additive change"
flask --app app.py db upgrade
pytest
```

Inspect generated SQL. Test against both fresh and upgraded legacy databases. Never make a destructive downgrade the default.

## Security reports

Follow [SECURITY.md](SECURITY.md). Do not open a public issue containing secrets, personal data, or an exploit against a live deployment.
