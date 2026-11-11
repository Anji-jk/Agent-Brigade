import json
from pathlib import Path

import pytest

from pipeline.publisher import transcript
from pipeline.publisher.chat import SYSTEM_MARKER, fix_prompt
from pipeline.publisher.transcript import (
    find_transcript,
    parse_transcript,
    project_folder_name,
    read_chat,
)

SAMPLE = Path(__file__).parent / "fixtures" / "transcript_sample.jsonl"
SESSION = "36849025-aeb6-40c9-8d9d-c6ed4d200016"
# A short working directory keeps the transcript folder name under the Windows path-length limit.
SHORT_CWD = Path("/work/Agent-Brigade")
WINDOWS_CWD = r"C:\Users\anjishnu.kumbhakar\OneDrive - JK Technosoft Ltd\Desktop\Agent-Brigade"


def lines(*records):
    return [json.dumps(r) for r in records]


def user(text, **extra):
    return {"type": "user", "timestamp": "t", "message": {"role": "user", "content": text}, **extra}


def answer(text, message_id="m1"):
    content = [{"type": "text", "text": text}]
    return {
        "type": "assistant",
        "timestamp": "t",
        "message": {"role": "assistant", "id": message_id, "content": content},
    }


def test_the_real_transcript_becomes_four_bubbles():
    bubbles = parse_transcript(SAMPLE.read_text(encoding="utf-8").splitlines())

    assert [b.role for b in bubbles] == ["user", "publisher", "user", "publisher"]
    assert bubbles[0].text.startswith("Employees should get an email reminder")
    assert bubbles[0].timestamp == "2026-11-11T10:58:19.657Z"
    assert bubbles[1].text.startswith("Epic chosen: SMT-2")
    assert bubbles[2].text.startswith("Keep it to one story")
    assert bubbles[3].text.startswith("Here is the updated proposal")
    for bubble in bubbles[1::2]:
        assert (
            "```plan" not in bubble.text and bubble.plan is not None and bubble.plan.startswith("{")
        )
    shown = "\n".join(b.text for b in bubbles)
    assert "Candidates: SMT-2" not in shown  # a note between tool calls, not the answer
    assert '"ok": true' not in shown and "python -m" not in shown  # no tool calls or output


def test_a_fix_request_is_hidden_and_the_corrected_answer_replaces_the_refused_one():
    bubbles = parse_transcript(
        lines(
            user("Add a reminder"),
            answer("Refused proposal", "m1"),
            user(fix_prompt(("no criteria",))),
            answer("Corrected proposal", "m2"),
            user("Thanks"),
            answer("You are welcome", "m3"),
        )
    )
    assert [(b.role, b.text) for b in bubbles] == [
        ("user", "Add a reminder"),
        ("publisher", "Corrected proposal"),
        ("user", "Thanks"),
        ("publisher", "You are welcome"),
    ]


def test_only_the_last_message_of_a_turn_is_the_answer_and_its_blocks_are_joined():
    bubbles = parse_transcript(
        lines(
            user("Hi"),
            answer("Looking things up.", "m1"),
            answer("Part one", "m2"),
            answer("part two", "m2"),
        )
    )
    assert bubbles[1].text == "Part one\n\npart two"


def test_side_chains_meta_messages_tool_results_and_broken_lines_are_skipped():
    tool_result = user([{"type": "tool_result", "content": "{}"}])
    raw = lines(
        user("Hi"),
        user("hidden", isMeta=True),
        user("side", isSidechain=True),
        tool_result,
        {"type": "summary", "summary": "x"},
        answer("Hello"),
    )
    bubbles = parse_transcript([*raw, '{"type": "assistant", "mess'])
    assert [(b.role, b.text) for b in bubbles] == [("user", "Hi"), ("publisher", "Hello")]


def test_user_content_given_as_text_blocks_is_read():
    bubbles = parse_transcript(lines(user([{"type": "text", "text": "From blocks"}])))
    assert bubbles[0].text == "From blocks"


def test_the_fix_prompt_starts_with_the_marker_the_reader_hides():
    assert fix_prompt(("x",)).startswith(SYSTEM_MARKER)


def test_folder_name_follows_claude_code():
    assert (
        project_folder_name(WINDOWS_CWD)
        == "C--Users-anjishnu-kumbhakar-OneDrive---JK-Technosoft-Ltd-Desktop-Agent-Brigade"
    )


def place(home, folder, session=SESSION):
    path = home / "projects" / folder / f"{session}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def test_the_transcript_is_found_in_the_folder_of_the_working_directory(tmp_path):
    cwd = SHORT_CWD
    path = place(tmp_path / "home", project_folder_name(cwd))
    assert find_transcript(SESSION, cwd, tmp_path / "home") == path
    chat = read_chat(SESSION, cwd, tmp_path / "home")
    assert chat is not None
    assert len(chat) == 4


def test_a_shortened_folder_name_is_found_one_level_down(tmp_path):
    path = place(tmp_path / "home", "C--Users-shortened-1a2b3c")
    assert find_transcript(SESSION, SHORT_CWD, tmp_path / "home") == path


def test_a_deleted_or_unknown_transcript_gives_none(tmp_path):
    (tmp_path / "home" / "projects" / "other").mkdir(parents=True)
    assert read_chat(SESSION, tmp_path, tmp_path / "home") is None
    assert read_chat(SESSION, tmp_path, tmp_path / "nowhere") is None


@pytest.mark.parametrize("bad", ["../../etc/passwd", "abc", "x" * 80, "a b c d e f g h"])
def test_a_session_id_that_could_point_elsewhere_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        find_transcript(bad, tmp_path, tmp_path)


def test_the_command_prints_the_bubbles(tmp_path, monkeypatch, capsys):
    cwd = SHORT_CWD
    place(tmp_path / "home", project_folder_name(cwd))
    monkeypatch.setattr(transcript, "REPO_ROOT", cwd)
    monkeypatch.setattr(transcript, "CLAUDE_HOME", tmp_path / "home")
    assert transcript.main([SESSION]) == 0
    out = capsys.readouterr().out
    assert out.count("--- user") == 2 and out.count("--- publisher") == 2 and "[+ plan]" in out


def test_the_command_reports_a_missing_transcript(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(transcript, "CLAUDE_HOME", tmp_path)
    assert transcript.main([SESSION]) == 1
    assert "No transcript" in capsys.readouterr().out


def test_an_attached_document_becomes_a_file_chip():
    from pipeline.publisher.attachments import message_with_files

    text = message_with_files("Use this", [("01-req.docx", "Long requirement text")])
    bubbles = parse_transcript(lines(user(text)))
    assert bubbles[0].text == "Use this" and bubbles[0].files == ("01-req.docx",)


def test_a_windows_message_with_crlf_still_becomes_a_file_chip():
    from pipeline.publisher.attachments import message_with_files

    text = message_with_files("Use this", [("01-req.docx", "Line 1\nLine 2")]).replace("\n", "\r\n")
    bubbles = parse_transcript(lines(user(text)))
    assert bubbles[0].text == "Use this" and bubbles[0].files == ("01-req.docx",)
