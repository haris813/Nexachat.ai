# Start here

## Fastest Windows run

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

The script creates `.venv` and `.env` when absent, installs runtime dependencies, applies database migrations, and starts `http://127.0.0.1:5000`.

The backend reads the repository-root `.env` file and uses OpenRouter by default. Add `OPENROUTER_API_KEY`, keep `AI_PROVIDER=openrouter`, and restart the process after changes. Search remains in demo mode and WhatsApp remains in mock mode unless separately configured.

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
