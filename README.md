# RSE Intelligence

Rwanda Stock Exchange Market Intelligence & Analytics Platform. Ingests official RSE
market report PDFs, extracts and validates structured market data (equities, bonds,
bond trades, indices, market statistics, exchange rates, closing bell), routes low-
confidence or conflicting values to an exception-based Review Center, and produces
analyst-ready Excel/CSV/PDF exports once a report is approved.

## Prerequisites

- **Python 3.10+** (this project was built and tested on 3.10). Check with `python --version`.
- **pip** (comes with Python).
- Nothing else is required to run it — SQLite is the default database, and there's no
  Redis/Celery/MySQL to install for local use.
- **Optional, only if you need it:**
  - **Tesseract OCR** — only needed if you'll upload *scanned* (image-only) PDFs. Native,
    text-based PDFs work without it. If Tesseract isn't installed, OCR is skipped
    cleanly (a validation issue is raised instead of the app crashing). Install it from
    https://github.com/UB-Mannheim/tesseract/wiki (Windows) and point `TESSERACT_CMD`
    in `.env` at `tesseract.exe` if it's not on your `PATH`.
  - **MySQL** — only needed for a production-style deployment. Point `DATABASE_URL` at
    it (see Configuration below); no code changes needed.

A `.venv` already exists in this project folder from development — you can reuse it
(skip straight to `.venv\Scripts\Activate.ps1`) or delete it and follow Quick Start
below to make your own.

## Quick Start (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env

flask --app run.py init-db
flask --app run.py create-admin

flask --app run.py run
```

`create-admin` prompts for name, email, and password. **Use a real-looking email
domain** (e.g. `you@gmail.com` or `admin@yourcompany.com`) — the email validator
rejects reserved/placeholder TLDs like `.test`, `.local`, `.example`, `.invalid`, so
something like `admin@rse.test` will silently fail login with "Invalid email or
password" and no other clue why.

If the interactive prompts misbehave in your terminal, create the account
non-interactively instead:

```powershell
python -c "from app import create_app; from app.extensions import db; from app.models.user import User; app = create_app('development'); ctx = app.app_context(); ctx.push(); u = User(name='Admin', email='YOUR_EMAIL_HERE', role='administrator', status='active'); u.set_password('YOUR_PASSWORD_HERE'); db.session.add(u); db.session.commit(); print('created', u.email)"
```

Then open http://127.0.0.1:5000 and sign in with the administrator account you created.

## Running Tests

```powershell
pytest
```

The integration and API test suites exercise the full pipeline (upload → extract →
validate → reconcile → approve → export) against a synthetic RSE-style PDF generated at
test time (`tests/fixtures/sample_report.py`) — no real official RSE report was
available when this platform was built, so extraction parsers were written against the
field/section definitions in the product spec rather than tuned to one real layout.

## Configuration

All configuration is via environment variables (see `.env.example`). By default the app
runs against a local SQLite database with zero external services required. For
production, set `DATABASE_URL` to a MySQL connection string
(`mysql+pymysql://user:password@host:3306/dbname`) — no code changes are needed.

## Architecture

- `app/models/` — SQLAlchemy models: users, reports, equities, bonds, bond trades,
  indices, market statistics, exchange rates, closing bell, extraction lineage,
  validation issues, corrections, audit log.
- `app/ingestion/` — the extraction pipeline: native text extraction (PyMuPDF), table
  extraction (pdfplumber), OCR fallback (pytesseract, degrades gracefully if Tesseract
  isn't installed), section classification, per-section parsers, deterministic
  normalizers/validators, cross-section reconciliation, and confidence scoring.
- `app/export/` — Excel (openpyxl), CSV, and PDF (reportlab) export.
- `app/api/` — JSON REST API.
- `app/views/` + `app/templates/` + `app/static/` — server-rendered dashboard, review
  center, equities/bonds/market pages (Bootstrap 5 + Chart.js).
- `app/services/` — audit logging, background task runner, duplicate detection,
  deterministic market insights, market narrative generation.

## Known Follow-Ups (not built in this pass)

- Phase 4 "Ask RSE Market" natural-language assistant.
- Swapping the in-process thread-pool task runner for real Celery + Redis (the
  `app/services/background_tasks.submit()` interface is already isolated for this).
- Tuning extraction parsers against a real official RSE PDF layout once one is
  available — see `app/ingestion/parsers/`.
