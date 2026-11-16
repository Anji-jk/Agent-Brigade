"""The message the Reviewer receives: the criteria and everything code measured, then the diff.

Every rule the Reviewer follows is in .claude/agents/reviewer.md. Here the facts are put into one
message: the numbered criteria, the files that changed, each check command with the end of its
output (and the output it had before the Builder, when it already failed then), what the Tester
did, the diff and the Builder's own report. The Reviewer cannot run anything, so it is told
what was measured, and it is told the diff may be cut.
"""

from typing import Any

from pipeline.checks.decide import OUTPUT_CHARS, VerifyResult

MAX_DIFF = 40_000
MAX_REPORT = 4_000
SHOWN_FILES = 60


def _tail(text: str, limit: int = OUTPUT_CHARS) -> str:
    text = (text or "").strip()
    return ("…" + text[-(limit - 1) :].lstrip()) if len(text) > limit else text or "(no output)"


def _how(result: VerifyResult) -> str:
    if result.passed:
        return "passed"
    return "did not finish in time" if result.timed_out else f"failed (exit {result.exit_code})"


def _verify_lines(results: list[VerifyResult], baseline_tails: dict[str, str]) -> list[str]:
    if not results:
        return ["(the task lists no check commands, or none was run)"]
    out: list[str] = []
    for r in results:
        out.append(f"### `{r.line}`: {_how(r)}")
        if r.baseline_failed:
            out.append("It also failed before the Builder changed anything. Output after:")
        elif not r.passed and r.baseline_failed is False:
            out.append("It PASSED before the Builder: this failure is new. Output after:")
        out += ["```", _tail(r.output_tail), "```"]
        if r.baseline_failed and r.line in baseline_tails:
            out += ["Output before the Builder:", "```", _tail(baseline_tails[r.line]), "```"]
    return out


def reviewer_prompt(
    task: dict[str, Any], *, changed: list[str], extra: list[str], verify: list[VerifyResult],
    baseline_tails: dict[str, str], tester_lines: list[str], diff: str, builder_report: str,
) -> str:  # fmt: skip
    """The first message of a Reviewer session for `task` (an entry of the plan)."""
    criteria = [f"{n}. {text}" for n, text in enumerate(task["acceptance_criteria"], start=1)]
    cut = len(diff) > MAX_DIFF
    shown = diff[:MAX_DIFF] + (
        f"\n... (diff cut at {MAX_DIFF} characters; Read the files)" if cut else ""
    )
    report = (builder_report or "").strip()[:MAX_REPORT] or "(no report)"
    files = [f"- {name}" for name in changed[:SHOWN_FILES]] or ["- (none)"]
    if len(changed) > SHOWN_FILES:
        files.append(f"- ... and {len(changed) - SHOWN_FILES} more")
    return "\n".join(
        [
            f"# {task.get('jira_key') or task['id']}: {task['title']}",
            "",
            "## Acceptance criteria (judge each one, by number)",
            *(criteria or ["(none)"]),
            "",
            "## Outcome",
            (task.get("expected_outcome") or "").strip() or "(none)",
            "",
            "## Files changed (measured by Git)",
            *files,
            *(
                ["", "Not in the task's Files list: " + ", ".join(extra[:SHOWN_FILES])]
                if extra
                else []
            ),
            "",
            "## Check commands (measured by Brigade, not claimed)",
            *_verify_lines(verify, baseline_tails),
            "",
            "## Tests",
            *(tester_lines or ["No Tester ran for this task."]),
            "",
            "## The Builder's report (what it says it did; not proof)",
            report,
            "",
            "## The diff",
            "```diff",
            shown or "(empty)",
            "```",
        ]
    )
