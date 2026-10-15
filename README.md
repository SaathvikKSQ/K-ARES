# K-AERS — Ksquare AI Evaluation, Reliability & Security Platform

Modular platform for evaluating AI applications (RAG, LLM apps, agents) on answer quality,
retrieval quality, reliability, latency, cost, and security. Specifications live in `specs/`
(spec-driven development; read `specs/constitution.md` first).

## Status — Phase 1 (Foundation) complete

- ✅ Backend: FastAPI + SQLAlchemy 2 + Alembic; health, auth (login/logout/me, roles), settings,
  JSON logging with secret redaction, request-id middleware, standard error envelope
- ✅ Full data model (applications, datasets, runs, results) migrated
- ✅ Frontend: React 18 + TS + Vite shell with routing, layout, login, empty states
- ✅ Docker Compose: api + postgres + web; ✅ backend pytest (20 tests), ruff clean; vitest

## Quickstart (Docker)

```bash
cp .env.example .env          # adjust SECRET_KEY / ADMIN_PASSWORD
docker compose up --build
# Web UI:      http://localhost:5173   (override with WEB_PORT)
# API docs:    http://localhost:8001/api/docs   (override with API_PORT; 8001 avoids clashing
#                                                with common local services on 8000)
# Health:      http://localhost:8001/api/v1/health
# Login with   ADMIN_EMAIL / ADMIN_PASSWORD from .env
```

## Quickstart (local, no Docker)

Backend (Python 3.11+):
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate                    # Windows (use source .venv/bin/activate on POSIX)
pip install -e ".[dev]"
set DATABASE_URL=sqlite:///./kaers.db     # PowerShell: $env:DATABASE_URL="sqlite:///./kaers.db"
alembic upgrade head
set ADMIN_EMAIL=admin@kaers.dev & set ADMIN_PASSWORD=dev-admin-123
python -m app.db.seed
uvicorn app.main:app --reload             # http://localhost:8000/api/docs
```

Frontend (Node 18+):
```bash
cd frontend
npm install
npm run dev                               # http://localhost:5173 (proxies /api to :8000)
```

## Commands

| Where | Command | Purpose |
|---|---|---|
| backend | `pytest` | Run backend tests |
| backend | `ruff check . && ruff format --check .` | Lint/format check |
| backend | `alembic upgrade head` | Apply migrations |
| backend | `python -m app.db.seed` | Seed initial admin (env-configured) |
| frontend | `npm run dev` / `build` / `test` / `typecheck` | Dev, build, vitest, type-check |

## Security notes

- All secrets come from environment variables; nothing is hardcoded. The API never returns
  credentials; logs are redacted (`specs/security/security-requirements.md`).
- Change `SECRET_KEY` and `ADMIN_PASSWORD` before any non-local deployment.
- Passing the (future) controlled security suite does not prove an application is secure.

## Roadmap

Phases and acceptance criteria: `specs/implementation/tasks.md`. Current phase: **1 of 6 done**;
Phase 2 (applications + datasets) is next.
