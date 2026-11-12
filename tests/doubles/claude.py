"""A fake Claude Code for tests: answers from a script and writes a transcript like the real one.

The transcript lines follow the real format read in pipeline.publisher.transcript (see
tests/pipeline/publisher/fixtures/transcript_sample.jsonl), so a test can send messages and then
open the chat again, the way the Publisher tab does. An answer may also be an exception (the
agent fails) or a function of the request (an agent that does something besides answering).
"""

import json
from collections.abc import Callable
from pathlib import Path

from pipeline.publisher.transcript import project_folder_name
from pipeline.runner.claude_runner import AgentError, AgentReply, AgentRequest


class FakeClaude:
    def __init__(
        self, claude_home: Path, *answers: str | Exception | Callable[[AgentRequest], str]
    ) -> None:
        self.claude_home = claude_home
        self.answers = list(answers)
        self.requests: list[AgentRequest] = []
        self._messages = 0

    def say(self, *answers: str | Exception | Callable[[AgentRequest], str]) -> "FakeClaude":
        self.answers.extend(answers)
        return self

    def transcript(self, request: AgentRequest) -> Path:
        folder = self.claude_home / "projects" / project_folder_name(request.cwd)
        return folder / f"{request.session_id}.jsonl"

    def run(self, request: AgentRequest) -> AgentReply:
        self.requests.append(request)
        path = self.transcript(request)
        if request.resume and not path.is_file():
            raise AgentError(f"No conversation found with session ID: {request.session_id}")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):  # an answer that also does something, as a misbehaving agent might
            answer = answer(request)
        self._messages += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            for record in (
                {"type": "user", "message": {"role": "user", "content": request.prompt}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "id": f"msg_{self._messages}",
                        "content": [{"type": "text", "text": answer}],
                    },
                },
            ):
                record.update(sessionId=request.session_id, timestamp="2026-11-11T12:00:00Z")
                out.write(json.dumps(record) + "\n")
        return AgentReply(
            text=answer, session_id=request.session_id, cost_usd=0.01, turns=3, duration_ms=1500
        )
