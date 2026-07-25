$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
mypy app scripts
pytest --cov=app --cov-report=term-missing
bandit -q -r app
pip-audit -r requirements.txt
python -m compileall -q app scripts tests app.py wsgi.py
node --check static/js/app.js
python scripts/validate_repo.py

Write-Host "NexaChat verification completed successfully." -ForegroundColor Green
