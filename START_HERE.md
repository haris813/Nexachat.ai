# Start here

## Fastest Windows run

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

The script creates `.venv` and `.env` when absent, installs runtime dependencies, applies database migrations, and starts `http://127.0.0.1:5000`.

The defaults use demo AI, demo search, and mock WhatsApp, so no credential or external delivery is required. To enable real providers, edit `.env` and follow [DEPLOYMENT.md](DEPLOYMENT.md).

## Full development setup

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
flask --app app.py db upgrade
python app.py
```

Run checks with `.\verify.ps1`. Run the complete stack with `docker compose up --build`.

Start with [README.md](README.md), then use the [demo walkthrough](docs/DEMO_WALKTHROUGH.md), [deployment guide](DEPLOYMENT.md), and [resume/interview guide](RESUME.md).
