"""Errors raised by tracker clients (Jira, GitHub)."""


class TrackerError(Exception):
    """A tracker could not be reached or refused a request. The message is safe to show."""
