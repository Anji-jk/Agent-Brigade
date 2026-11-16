import pytest

from pipeline.checks import testfiles as t


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/test_a.py", True),
        ("backend/tests/helpers.py", True),
        ("frontend/src/__tests__/App.js", True),
        ("src/components/Button.test.jsx", True),
        ("src/components/Button.spec.ts", True),
        ("pkg/user_test.go", True),
        ("src/main/java/UserServiceTest.java", True),
        ("test_utils.py", True),
        ("src/latest.java", False),
        ("src/contest.py", False),
        ("frontend/src/index.css", False),
        ("backend/main.py", False),
        ("docs/testing-guide.md", False),
    ],
)
def test_a_test_file_is_known_by_its_place_or_its_name(path, expected):
    assert t.is_test_path(path) is expected


def test_the_test_places_a_task_lists_are_found():
    listed = ["src/app.py", "tests/", "src/a.test.js", "qa/check_app.py"]
    assert t.listed_test_paths(listed) == ["tests", "src/a.test.js"]


def test_what_the_tester_changed_outside_tests_is_listed():
    changed = ["tests/test_a.py", "src/app.py", "src/app.test.js", "qa/check_app.py"]
    assert t.writes_outside_tests(changed) == ["qa/check_app.py", "src/app.py"]


@pytest.mark.parametrize(
    "text",
    [
        "def test_a():\n    assert 1",
        "  async def test_b():\n    pass",
        "class TestThing:\n    pass",
        "describe('x', () => {})",
        "  it.each([1])('works', () => {})",
        "test('works', () => {})",
        "@Test\nvoid works() {}",
        "func TestWorks(t *testing.T) {}",
        "#[test]\nfn works() {}",
        "[Fact]\npublic void Works() {}",
        "Describe 'the script' {}",
    ],
)
def test_a_file_that_declares_a_test_holds_one(text):
    assert t.holds_a_test(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Write-Host 'run the app'\n",
        "def helper():\n    assert 1\n",
        "import pytest\n\n@pytest.fixture\ndef thing(): ...\n",
        "const contest = 1; // test the waters\n",
        "export function expect(x) { return x }\n",
    ],
)
def test_a_file_without_a_test_declaration_holds_none(text):
    assert t.holds_a_test(text) is False


@pytest.mark.parametrize(
    ("name", "file"),
    [
        ("tests/test_a.py::test_one", "tests/test_a.py"),
        ("tests/a.test.js", "tests/a.test.js"),
        (" tests\\a.test.js ", "tests/a.test.js"),
    ],
)
def test_the_file_is_taken_out_of_a_test_name(name, file):
    assert t.test_file_of(name) == file


def test_a_name_must_be_a_test_file_that_the_tester_wrote():
    wrote = ["tests/test_a.py", "src/app.py"]
    problems = t.named_test_problems(
        [
            "tests/test_a.py::test_one",
            "tests/test_missing.py",
            "src/app.py",
            "../tests/x.py",
            "-k",
        ],
        wrote,
    )
    assert problems == [
        "tests/test_missing.py: the Tester did not write this file",
        "src/app.py: not in a test location",
        "../tests/x.py: not a path inside the project",
        "-k: not a path inside the project",
    ]


DIFF = """\
diff --git a/tests/test_a.py b/tests/test_a.py
index 1..2 100644
--- a/tests/test_a.py
+++ b/tests/test_a.py
@@ -3,2 +3,1 @@
-import os
-def test_one():
-    assert f() == 1
+def test_one():
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-def test_helper():
+def test_helper2():
diff --git a/web/a.test.js b/web/a.test.js
--- a/web/a.test.js
+++ b/web/a.test.js
@@ -1 +1 @@
-import x from "x";
+import y from "y";
diff --git a/web/b.test.js b/web/b.test.js
--- a/web/b.test.js
+++ b/web/b.test.js
@@ -1 +1 @@
-  expect(a).toBe(1);
+  expect(a).toBe(2);
"""


def test_a_test_file_that_lost_a_test_or_an_assertion_is_reported():
    # tests/test_a.py lost a def and an assert; b.test.js had an expect rewritten;
    # an import change (a.test.js) and a non-test file (src/app.py) are not reported.
    assert t.files_that_lost_tests(DIFF) == ["tests/test_a.py", "web/b.test.js"]


@pytest.mark.parametrize(
    "line",
    [
        "-    it('does a thing', () => {",
        "-    test.each([1, 2])('x', () => {})",
        "-describe('group', () => {",
        "-    @Test",
        "-    assertEquals(1, f());",
        "-func TestUser(t *testing.T) {",
        '-    t.Run("case", func(t *testing.T) {',
    ],
)
def test_the_declarations_of_the_common_test_tools_are_known(line):
    diff = f"diff --git a/x/a.test.js b/x/a.test.js\n--- a/x/a.test.js\n@@ -1 +0,0 @@\n{line}\n"
    assert t.files_that_lost_tests(diff) == ["x/a.test.js"]
