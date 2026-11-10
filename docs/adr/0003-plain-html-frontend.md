# 0003 Plain HTML and JavaScript frontend

Status: accepted, 10 Nov 2026.

## Decision
`frontend/` is plain HTML, CSS and JavaScript modules, served by FastAPI. No build step, no Node.

## Why
- The technical document asks for it: any developer can change a screen without a toolchain.
- The app runs only on the developer's machine, so bundle size and server rendering do not matter.

## Consequences
- One JavaScript module per tab in `frontend/js/tabs/`; shared pieces in `frontend/js/components/`.
- Live updates use one `EventSource` on `/api/events/stream`, not polling.
- If screens grow beyond what modules handle comfortably, revisit; a framework can replace the
  tab modules without touching the backend.
