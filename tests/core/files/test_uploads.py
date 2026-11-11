import pytest

from core.files import uploads


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Renewal Rules.docx", "Renewal Rules.docx"),
        (r"C:\Users\me\Desktop\notes.MD", "notes.md"),
        ("../../brigade.db.txt", "brigade.db.txt"),
        ("req:v2?*.pdf", "req_v2.pdf"),
        ("...", "file"),
        ("a" * 300 + ".pdf", "a" * 96 + ".pdf"),
    ],
)
def test_names_lose_folders_and_unsafe_characters(name, expected):
    assert uploads.safe_name(name) == expected


def test_files_are_numbered_saved_listed_and_found(tmp_path):
    names = uploads.stored_names(["a.txt", "a.txt"])
    assert names == ["01-a.txt", "02-a.txt"]
    for name in names:
        uploads.save(tmp_path, 7, name, b"data")
    assert uploads.stored_names(["b.pdf"], already=2) == ["03-b.pdf"]

    listed = uploads.list_files(tmp_path, 7)
    assert [(f.stored_name, f.name, f.size) for f in listed] == [
        ("01-a.txt", "a.txt", 4),
        ("02-a.txt", "a.txt", 4),
    ]
    assert uploads.find(tmp_path, 7, "02-a.txt") == tmp_path / "PUB-000007" / "02-a.txt"


def test_only_files_of_that_chat_can_be_found(tmp_path):
    uploads.save(tmp_path, 1, "01-a.txt", b"x")
    (tmp_path / "secret.txt").write_text("no")
    assert uploads.find(tmp_path, 1, "../secret.txt") is None
    assert uploads.find(tmp_path, 2, "01-a.txt") is None
    assert uploads.list_files(tmp_path, 3) == []


def test_a_name_that_is_not_a_stored_name_is_not_saved(tmp_path):
    with pytest.raises(ValueError):
        uploads.save(tmp_path, 1, "../evil.txt", b"x")
