# Agent Brigade

Multi-agent orchestration platform: Jira stories in, verified code out.

Status: Phase 0 (repo skeleton). Nothing runs yet; the folders, packaging, CI and the layer rule are in place.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

All three checks pass on a fresh clone. CI runs the same three.

## Layout

| Folder | Holds |
| --- | --- |
| `.claude/agents/` | The six agent definitions |
| `frontend/` | Plain HTML + JS page, no build step |
| `backend/` | FastAPI routes and use cases |
| `pipeline/` | The orchestrator |
| `core/` | Settings, database, trackers, locks |
| `tests/` | Tests, mirroring the source |
| `docs/` | Technical document, database schema, screens, decision records |

Imports point down: `core` < `pipeline` < `backend`. See `CLAUDE.md` for the rules.

## Where to read next

- `docs/technical-document.md`: what is being built and why
- `docs/database.dbml`: the schema (paste into https://dbdiagram.io/d)
- `docs/screens/`: the UI screenshots
- `docs/adr/`: decisions made so far and the reason for each