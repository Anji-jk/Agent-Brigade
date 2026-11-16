"""Rules about where an attempt's changes may be. Pure: no Git, no files, nothing is run.

A task names the files it expects to touch. Touching others is allowed, since a plan cannot see
everything, but they are measured and handed to the Reviewer. A few places are different: an
attempt may never change them unless its task lists them by name.
"""

from collections.abc import Iterable
from pathlib import PurePosixPath

PROTECTED_FOLDERS = (".agent-brigade", ".claude")
GUIDE_FILE = "CLAUDE.md"
ENV_TEMPLATE_ENDINGS = (".example", ".sample", ".template")


def normalize(path: str) -> str:
    """A path in Git's own form: forward slashes, no leading ./, "" for the project root."""
    text = PurePosixPath(path.replace("\\", "/")).as_posix().removeprefix("./")
    return "" if text == "." else text


def under(path: str, places: Iterable[str]) -> bool:
    """Is `path` one of `places`, or inside one that is a folder? An empty place means anywhere."""
    path = normalize(path)
    for place in map(normalize, places):
        if not place or path == place or path.startswith(place.rstrip("/") + "/"):
            return True
    return False


def is_secret_file(path: str) -> bool:
    """A .env file, in any folder. The templates people commit (.env.example) do not count."""
    name = PurePosixPath(normalize(path)).name
    is_env = name == ".env" or name.startswith(".env.")
    return is_env and not name.endswith(ENV_TEMPLATE_ENDINGS)


def protected(changed: Iterable[str], task_files: Iterable[str]) -> list[str]:
    """Changed paths the task had no right to touch: any .env file, .agent-brigade/, .claude/,
    and a CLAUDE.md unless the task lists that path itself."""
    listed = {normalize(path) for path in task_files}
    found = []
    for path in map(normalize, changed):
        name = PurePosixPath(path).name
        if is_secret_file(path) or under(path, PROTECTED_FOLDERS):
            found.append(path)
        elif name == GUIDE_FILE and path not in listed:
            found.append(path)
    return sorted(found)


def extra_files(changed: Iterable[str], task_files: Iterable[str]) -> list[str]:
    """Changed paths the task did not list. A listed folder covers what is inside it.

    A task that lists no files gives nothing to compare with, so nothing is extra.
    """
    listed = list(task_files)
    if not listed:
        return []
    return sorted(normalize(path) for path in changed if not under(path, listed))
