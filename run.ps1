if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env. Add OPENROUTER_API_KEY before using AI chat." -ForegroundColor Yellow
}
flask --app app.py db upgrade
python app.py
