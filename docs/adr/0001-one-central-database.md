# 0001 One central database

Status: accepted, 10 Nov 2026. Changes technical document section 11.

## Decision
One SQLite file, `<BRIGADE_DATA_DIR>/brigade.db` (default `~/.agent-brigade/`), holds every
connected project. The project selector on every screen filters by `project_id`.

## Why
- The screens show a project selector, so one view across projects needs one store.
- One Jira site hosts many spaces; a story key like KAN-10 is already unique across the site.

## Consequences
- Per-project settings (Jira space key, repository, local path, base branch, tracker) move from
  `.env` into the `projects` table. Secrets stay in `.env`.
- Turn on WAL mode and keep transactions short: SQLite allows one writer at a time.
- Files people or agents read directly (`plan.json`, `events.jsonl`, `reports/`) stay in the
  target project's `.agent-brigade/` folder.
- Copying a project folder no longer carries its history.
- Open: `BRIGADE_GITHUB_TOKEN` is one per repository. With several projects on GitHub, store the
  name of an environment variable per project, never the token.
