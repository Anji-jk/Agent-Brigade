"""The two documentation agents are sources of an attempt, and their record is a stage report."""

from pipeline.feed import reports, sources
from tests.pipeline.feed.test_feed_sources import make_attempt
from tests.pipeline.stages.stage_setup import RUN


def test_the_documenter_and_its_reviewer_have_their_own_tabs(tmp_path):
    make_attempt(tmp_path, roles=("documenter", "doc-reviewer"))
    found = sources.available(tmp_path, RUN, "SMT-62", 1)
    assert found == ["orchestrator", "documenter", "doc-reviewer"]
    first = sources.attempt_items(tmp_path, RUN, "SMT-62", 1, "doc-reviewer")
    assert first[0].kind == "start"


def test_a_build_attempt_has_no_documentation_tabs(tmp_path):
    make_attempt(tmp_path, roles=("builder", "reviewer"))
    assert not {"documenter", "doc-reviewer"} & set(sources.available(tmp_path, RUN, "SMT-62", 1))


def test_the_docs_report_has_what_was_written_and_what_was_refused(tmp_path):
    from core.files.atomic import write_json_atomic
    from pipeline.stages.stage_inputs import report_path

    write_json_atomic(
        report_path(tmp_path, RUN, "docs", "SMT-62", 1),
        {
            "ok": False, "error": None, "wrote": ["docs/a.md"], "outside": ["README.md"],
            "report": "wrote it", "run_id": RUN, "usage": {"turns": 2, "session_id": "x"},
            "limits": {"max_turns": 30}, "finished_at": "t",
        },
    )  # fmt: skip
    body = reports.stage_report(tmp_path, RUN, "SMT-62", 1, "docs")
    assert body["wrote"] == ["docs/a.md"] and body["outside"] == ["README.md"]
    assert body["ok"] is False and body["report"] == "wrote it"
    assert "run_id" not in body and "session_id" not in body["usage"]
