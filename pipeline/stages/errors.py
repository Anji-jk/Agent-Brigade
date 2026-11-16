"""The error every build stage raises when it refuses to start. The message says why."""


class BuildError(RuntimeError):
    """The stage was refused before anything ran. The message says why and what to do."""
