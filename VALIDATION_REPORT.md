# Validation report

Validation date: 2026-07-24

## Passed

- Ruff formatting and lint: clean
- mypy: 22 application/operations modules, no issues
- pytest: 27 passed
- coverage: 70% overall; core models 98%, chat API 87%, artifact service 88%
- Bandit application scan: clean
- `pip-audit`: no known vulnerabilities after upgrading cryptography to 48.0.1
- Python compile and frontend JavaScript syntax checks: clean
- Repository structure: 6 JSON files, 10 YAML files, and 103 JavaScript-to-HTML DOM references validated
- Fresh SQLite migration: revision `20260724_0001`, 14 tables, all legacy/workspace tables present
- Compose configuration: parses successfully
- Artifact structure: XLSX, PPTX, DOCX, and PDF reopened with their native Python libraries; source metadata and expected structure verified
- Artifact visuals: 5/5 PowerPoint slides exported with native PowerPoint and inspected; 3/3 PDF pages rendered and inspected; no clipping or overlap found
- Formula-injection, invalid-file, SSRF, owner-isolation, current-data refusal, prompt-boundary, contact-import savepoint, authentication, research citation, and WhatsApp confirmation tests passed
- Local health benchmark: 50 requests, concurrency 5, zero failures, mean 81.8 ms, p50 33.5 ms, p95 323.9 ms, max 799.1 ms on the development server

## Environment limitations

- Docker Compose resolves, but Docker Desktop’s Linux engine was stopped, so the image build was not executed locally. CI retains an independent BuildKit image-build job.
- LibreOffice is unavailable. Native PowerPoint rendering succeeded; native Word/Excel COM export was unreliable headlessly. DOCX/XLSX therefore passed structural/native-library validation but not the visual render gate in this environment. Open representative files manually or render them in CI/release infrastructure before a public release.
- Real OpenAI, live-search, and Meta WhatsApp credentials were not used. Provider adapters are covered by mocks and safe no-key modes; credentialed smoke tests remain an operator release step.

## Reproduce

```powershell
.\verify.ps1
python -m pip_audit -r requirements.txt
docker compose config
docker build -t nexachat-ai:release .
python scripts/benchmark.py --requests 50 --concurrency 5
```
