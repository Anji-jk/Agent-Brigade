"""Where a story run stands as a build: derived from the processes and files, not from a status.

not_started   nobody has launched a loop for it
running       a loop process of this run is running now
finished      its loop ended with every task merged
stopped       its loop ended with a task not merged (failed, blocked, or waiting for a person)
paused        its loop ended with a task a person Stopped: Continue goes on from where it was
interrupted   a loop was started, its process is gone and it left no report (a crash, a restart)

A status saved in the database would go stale the moment the loop dies, because nothing is left
to update it. The process and the report cannot.
"""

import json
from pathlib import Path

from pipeline.control.launch import loop_alive, read_launch
from pipeline.control.processes import CommandLine, command_line
from pipeline.stages.story_report import FILE as REPORT_FILE

NOT_STARTED, RUNNING, FINISHED, STOPPED, PAUSED, INTERRUPTED = (
    "not_started",
    "running",
    "finished",
    "stopped",
    "paused",
    "interrupted",
)


def _report(run_dir: Path) -> dict | None:
    """The loop's report, or None when there is no readable one."""
    try:
        data = json.loads((Path(run_dir) / REPORT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _ended(report: dict) -> str:
    """How a loop that wrote a report ended."""
    if report.get("ok"):
        return FINISHED
    tasks = report.get("tasks")
    statuses = [t.get("status") for t in tasks.values() if isinstance(t, dict)] if tasks else []
    return PAUSED if "stopped" in statuses else STOPPED


def build_state(run_dir: Path, run_id: str, get_command_line: CommandLine = command_line) -> str:
    if loop_alive(run_dir, run_id, get_command_line):
        return RUNNING
    report = _report(run_dir)
    if report is not None:
        return _ended(report)
    return INTERRUPTED if read_launch(run_dir) else NOT_STARTED