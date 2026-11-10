# 0002 Three Python packages with one-way imports

Status: accepted, 10 Nov 2026.

## Decision
`core` (settings, database, trackers) < `pipeline` (the orchestrator) < `backend` (FastAPI).
A lower package never imports a higher one. `tests/test_layers.py` enforces it.

## Why
- The orchestrator must run and be tested without the web server, so `pipeline` cannot import `backend`.
- The backend and the orchestrator both need the database and Jira. Putting that in `core` avoids
  either importing the other.

## Consequences
- Top-level names `core`, `pipeline` and `backend` are generic. In Python `import core` loads
  the first module of that name found, so a library with the same top-level name could shadow
  ours. Agent Brigade runs in its own virtual environment, so this is unlikely. If it happens,
  move all three under one `brigade/` package.
