if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env. Demo AI, demo search, and mock WhatsApp are ready without credentials." -ForegroundColor Green
}
flask --app app.py db upgrade
python app.py
