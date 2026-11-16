import json

from pipeline.feed.agent_stream import agent_items
from pipeline.feed.tool_text import PathTrimmer, tool_title

CWD = "C:\\bw\\SMT-61-x\\SMT-62-1"
INIT = {
    "type": "system",
    "subtype": "init",
    "cwd": CWD,
    "model": "claude-sonnet-5-5",
    "tools": ["Read", "Edit"],
    "permissionMode": "acceptEdits",
}


def tool_use(tool_id, name, **data):
    block = {"type": "tool_use", "id": tool_id, "name": name, "input": data}
    return {"type": "assistant", "message": {"id": "m" + tool_id, "content": [block]}}


def tool_result(tool_id, content, is_error=False):
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": content}
    if is_error:
        block["is_error"] = True
    return {"type": "user", "message": {"content": [block]}}


def write(tmp_path, events, times=None):
    path = tmp_path / "builder.events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    if times is not None:
        (tmp_path / "builder.events.times").write_text("\n".join(times) + "\n", encoding="utf-8")
    return path


def test_the_session_start_names_the_model_and_the_tools(tmp_path):
    (start,) = agent_items(write(tmp_path, [INIT]))
    assert start.kind == "start"
    assert start.title == "session started · claude-sonnet-5-5 · 2 tools"
    assert "permission mode: acceptEdits" in start.detail


def test_a_tool_call_is_paired_with_its_result_and_shows_the_path_inside_the_worktree(tmp_path):
    read = tool_use("t1", "Read", file_path=CWD + "\\frontend\\src\\index.css")
    items = agent_items(write(tmp_path, [INIT, read, tool_result("t1", "a\nb\nc\n")]))
    call = items[1]
    assert (call.kind, call.tool, call.title) == ("tool", "Read", "frontend/src/index.css")
    assert call.result["summary"] == "3 lines" and not call.pending


def test_a_call_without_a_result_yet_is_pending(tmp_path):
    (call,) = agent_items(write(tmp_path, [tool_use("t1", "Bash", command="npm run build")]))
    assert call.pending and call.title == "npm run build"


def test_a_failed_result_is_an_error_and_a_refused_one_is_blocked(tmp_path):
    events = [
        tool_use("t1", "Bash", command="x"),
        tool_result("t1", "boom", is_error=True),
        tool_use("t2", "Edit", file_path="a.py", old_string="1", new_string="2"),
        tool_result("t2", "Permission to edit was denied", is_error=True),
    ]
    first, second = agent_items(write(tmp_path, events))
    assert first.result["status"] == "error"
    assert second.result["status"] == "blocked"
    assert "--- before\n1\n+++ after\n2" in second.detail


def test_what_the_agent_said_is_shown_once_even_when_claude_repeats_the_message(tmp_path):
    said = {"type": "text", "text": "I will read the file.\nThen edit it."}
    message = {"type": "assistant", "message": {"id": "m1", "content": [said]}}
    items = agent_items(write(tmp_path, [message, message]))
    assert len(items) == 1
    assert items[0].kind == "say" and items[0].title == "I will read the file."
    assert items[0].detail.endswith("Then edit it.")


def test_the_end_of_the_run_shows_turns_cost_and_time(tmp_path):
    done = {
        "type": "result",
        "subtype": "success",
        "num_turns": 14,
        "total_cost_usd": 0.1449,
        "duration_ms": 81200,
        "result": "all done",
    }
    (end,) = agent_items(write(tmp_path, [done]))
    assert end.kind == "finish" and end.title == "succeeded · 14 turns · $0.1449 total · 81.2s"


def test_a_failed_run_is_an_error(tmp_path):
    (end,) = agent_items(write(tmp_path, [{"type": "result", "subtype": "error_max_turns"}]))
    assert end.kind == "error" and end.status == "error"


def test_system_chatter_other_than_the_start_is_left_out(tmp_path):
    chatter = [{"type": "system", "subtype": s} for s in ("hook_started", "task_started", "status")]
    assert agent_items(write(tmp_path, [*chatter, {"type": "stream_event"}])) == []


def test_a_rate_limit_warning_and_a_block_are_shown(tmp_path):
    warn = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning"}}
    block = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}
    ok = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}}
    items = agent_items(write(tmp_path, [warn, block, ok]))
    assert [(i.kind, i.status) for i in items] == [("step", "warn"), ("error", "error")]


def test_each_line_gets_its_time_from_the_times_file(tmp_path):
    read = tool_use("t1", "Read", file_path="a.py")
    path = write(
        tmp_path, [INIT, read], times=["2026-11-16T09:49:41+00:00", "2026-11-16T09:49:44+00:00"]
    )
    assert [i.at for i in agent_items(path)] == [
        "2026-11-16T09:49:41+00:00",
        "2026-11-16T09:49:44+00:00",
    ]


def test_a_time_inside_the_event_wins_over_the_times_file(tmp_path):
    read = {**tool_use("t1", "Read", file_path="a.py"), "timestamp": "2026-11-16T09:50:00Z"}
    (call,) = agent_items(write(tmp_path, [read], times=["2026-11-16T09:49:44+00:00"]))
    assert call.at == "2026-11-16T09:50:00Z"


def test_a_torn_last_line_does_not_hide_the_rest(tmp_path):
    path = write(tmp_path, [INIT])
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"type": "assistant", "mess')
    assert len(agent_items(path)) == 1


def test_a_missing_file_has_no_items(tmp_path):
    assert agent_items(tmp_path / "none.events.jsonl") == []


def test_tool_titles():
    trim = PathTrimmer()
    assert tool_title("Write", {"file_path": "a.py", "content": "1\n2\n"}, trim) == "a.py (2 lines)"
    assert tool_title("Grep", {"pattern": "foo", "path": "src"}, trim) == "foo  in src"
    assert tool_title("Glob", {"pattern": "**/*.py"}, trim) == "**/*.py"
    assert tool_title("WebFetch", {"url": "https://x.io"}, trim) == "https://x.io"
    assert tool_title("Other", {}, trim) == ""
