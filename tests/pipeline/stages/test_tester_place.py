from pipeline.stages import tester_place as tp


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return name


def test_a_test_the_task_lists_is_a_place_without_reading_anything(tmp_path):
    place = tp.find_place(tmp_path, ["src/a.py", "tests/test_new.py"], [])
    assert place.found and place.listed == ["tests/test_new.py"] and place.reason() == ""


def test_a_script_in_a_test_folder_is_named_like_a_test_but_is_not_one(tmp_path):
    script = write(tmp_path, "scripts/test/test-app.ps1", "Write-Host 'run the app'\n")
    other = write(tmp_path, "frontend/src/App.jsx", "export default 1\n")
    place = tp.find_place(tmp_path, ["src/a.py"], [script, other])
    assert not place.found and place.empty == [script]
    assert place.reason() == (
        "the task lists no test file, and none of the project's 1 test-named file(s) "
        "declares a test (scripts/test/test-app.ps1)."
    )


def test_one_real_test_among_empty_ones_is_a_place(tmp_path):
    helper = write(tmp_path, "tests/conftest.py", "import pytest\n")
    real = write(tmp_path, "tests/test_a.py", "def test_a():\n    assert True\n")
    place = tp.find_place(tmp_path, [], [helper, real, real])
    assert place.found and place.real == [real] and place.empty == [helper]


def test_a_project_without_any_test_file_says_so(tmp_path):
    place = tp.find_place(tmp_path, ["src/a.py"], ["src/a.py"])
    assert not place.found
    assert place.reason() == "the task lists no test file and the project has no test files."


def test_the_reason_names_only_the_first_files(tmp_path):
    names = [write(tmp_path, f"test/s{n}.ps1", "x\n") for n in range(7)]
    reason = tp.find_place(tmp_path, [], names).reason()
    assert "7 test-named" in reason and "test/s4.ps1, ...)" in reason and "s5" not in reason


def test_a_missing_or_unreadable_file_holds_no_test(tmp_path):
    place = tp.find_place(tmp_path, [], ["tests/test_gone.py"])
    assert place.empty == ["tests/test_gone.py"] and not place.found
