"""Move an issue to a status by NAME, through Jira's transitions.

Jira moves issues by transition, not by status. A transition is found by the status it leads
to. When the workflow has no direct way to the target, one middle status may be used (To Do
cannot always go straight to Done, but In Progress usually can).
"""

from core.trackers.jira.client import JiraClient, JiraError


class NoPath(JiraError):
    """The workflow gives no way to the wanted status from where the issue is."""


def _to(client: JiraClient, key: str, target: str) -> str | None:
    wanted = target.strip().lower()
    return next((tid for tid, name in client.transitions(key) if name.lower() == wanted), None)


def move_to(
    client: JiraClient,
    key: str,
    target: str,
    via: str | None = None,
    current: str | None = None,
) -> None:
    """Move `key` to `target`. `current` is the status it is in now: if the way through `via`
    turns out to be closed, the issue is put back there instead of being left half way."""
    direct = _to(client, key, target)
    if direct:
        client.transition(key, direct)
        return
    middle = _to(client, key, via) if via and via.lower() != target.lower() else None
    if middle:
        client.transition(key, middle)  # Jira only shows the next step once this one is taken
        last = _to(client, key, target)
        if last:
            client.transition(key, last)
            return
        back = _to(client, key, current) if current else None
        if back:
            client.transition(key, back)
    raise NoPath(f"{key}: the workflow has no way to {target} from its status.")
