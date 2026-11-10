# 0004 Agent definitions live in .claude/agents/

Status: accepted, 10 Nov 2026.

## Decision
The six agents are Markdown files in this repository's `.claude/agents/`. The header sets name,
description, tools, model, effort and max turns; the body is the prompt. The runner reads a file
and passes its settings to Claude Code on the command line.

## Why
- One file per agent means a model or tool change touches no code (technical document section 9).
- The agents belong to the platform, not to any target project, so they work for every project.

## Consequences
- Opening Claude Code on this repository also shows these six as subagents. Be aware of it when
  developing Agent Brigade itself.
- Target projects keep their own rules in their own `CLAUDE.md`, which agents read.
