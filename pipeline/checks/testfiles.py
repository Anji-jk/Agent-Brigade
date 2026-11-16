"""Which files are tests, where the Tester may write, and which tests a change took away.

Pure: no Git, no files, nothing is run. Brigade does not know a project's language, so a test
file is recognised by habit, which Python, Node, Java, Go and most others share: a folder called
tests, test, __tests__ or spec, or a file name such as test_x.py, x_test.go, x.test.js,
x.spec.ts or XTest.java. A task lists the Builder's files too, so what a task lists never makes
a file a test: only habit does.
"""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from pipeline.checks.paths import normalize

TEST_FOLDER_NAMES = frozenset({"tests", "test", "__tests__", "spec", "specs"})
_TEST_NAME = re.compile(
    r"^test_.+|.+_test\..+|.+\.(test|spec)\..+|.+(?-i:Tests?)\.(java|kt|cs|scala)$",
    re.IGNORECASE,
)
# A line that declares a test or states what it expects: pytest, unittest, jest and vitest,
# mocha, JUnit and Go. Taking one of these away is how a change makes a failing suite pass.
_DECLARATION = re.compile(
    r"\s*("
    r"(async\s+)?def\s+test|class\s+Test|assert\w*\b"
    r"|(it|test|describe)(\.\w+)*\s*\(|expect\s*\("
    r"|@(Parameterized)?Test\b|func\s+Test\w*\s*\(|t\.(Run|Error|Errorf|Fatal|Fatalf)\s*\("
    r")",
)


# What a file must contain to hold a test, not only to be named like one. Narrower than
# _DECLARATION: a bare assert or expect( also appears in ordinary code. pytest, unittest, jest,
# vitest, mocha, JUnit, NUnit and xUnit, Go, Rust and Pester.
_HOLDS_A_TEST = re.compile(
    r"^\s*(async\s+)?def\s+test|^\s*class\s+Test|^\s*(it|test|describe)(\.\w+)*\s*\("
    r"|@(Parameterized)?Test\b|func\s+Test\w*\s*\(|#\[test\]|^\s*\[(Fact|Test|TestMethod)\]"
    r"|^\s*(Describe|It)\s+['\"]",
    re.MULTILINE,
)


def is_test_path(path: str) -> bool:
    """A test file, or a test folder, by its place and its name."""
    parts = normalize(path).split("/")
    if any(part.lower() in TEST_FOLDER_NAMES for part in parts):
        return True
    return bool(_TEST_NAME.match(PurePosixPath(parts[-1]).name))


def listed_test_paths(task_files: Iterable[str]) -> list[str]:
    """The test files and folders the task itself lists."""
    return [normalize(path) for path in task_files if path.strip() and is_test_path(path)]


def writes_outside_tests(changed: Iterable[str]) -> list[str]:
    """What the Tester changed that is not a test location."""
    return sorted(normalize(path) for path in changed if not is_test_path(path))


def holds_a_test(text: str) -> bool:
    """Does this file's text declare at least one test (a name alone proves nothing)."""
    return bool(_HOLDS_A_TEST.search(text))


def test_file_of(name: str) -> str:
    """The file in a test name such as tests/test_a.py::test_one or tests/a.test.js."""
    return normalize(name.split("::", 1)[0].strip())


def named_test_problems(names: Iterable[str], existing: Iterable[str]) -> list[str]:
    """Why a test name the Tester gave cannot be used: not a file in a test place, or not there.

    `existing` is every path in the worktree that the Tester wrote or changed, because a test
    the Tester names must be one it made.
    """
    made = {normalize(path) for path in existing}
    problems = []
    for name in dict.fromkeys(names):
        path = test_file_of(name)
        if not path or path.startswith("/") or ".." in path.split("/") or path.startswith("-"):
            problems.append(f"{name}: not a path inside the project")
        elif not is_test_path(path):
            problems.append(f"{name}: not in a test location")
        elif path not in made:
            problems.append(f"{name}: the Tester did not write this file")
    return problems


def files_that_lost_tests(diff: str) -> list[str]:
    """Test files that lost a test or an assertion, read from `git diff HEAD -U0` text.

    Adding tests is expected, and so is touching an import or a helper in a test file. Removing
    or rewriting a declaration or an assertion is reported, even if a similar line was added.
    """
    flagged: set[str] = set()
    current: str | None = None
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current, in_hunk = None, False
        elif not in_hunk and line.startswith("--- a/"):
            current = normalize(line[len("--- a/") :])
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and current and line.startswith("-") and _DECLARATION.match(line[1:]):
            if is_test_path(current):
                flagged.add(current)
    return sorted(flagged)
