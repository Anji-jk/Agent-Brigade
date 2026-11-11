"""Attached documents inside a Publisher message.

The agent has no file access, so the text of each attached document is put into the message,
between two marker lines that name the file:

    [Attached file: 01-requirements.docx]
    ...the document's text...
    [End of attached file: 01-requirements.docx]

Previous Chats shows such a block as a file chip, not as the text. A document cannot fake a
marker or a Brigade system note: those lines are removed from its text first.
"""

import re

from pipeline.publisher.chat import SYSTEM_MARKER
from pipeline.publisher.publish import NOTE_END, NOTE_START

START = "[Attached file: {name}]"
END = "[End of attached file: {name}]"
BLOCK = re.compile(
    r"\[Attached file: (?P<name>[^\]\n]+)\]\n.*?\n\[End of attached file: (?P=name)\]",
    re.DOTALL,
)
FORGED = re.compile(
    r"^.*(\[Attached file:|\[End of attached file:|"
    + "|".join(re.escape(m) for m in (SYSTEM_MARKER, NOTE_START, NOTE_END))
    + r").*$",
    re.MULTILINE,
)


def wrap(stored_name: str, text: str) -> str:
    """One document's text between its markers."""
    clean = FORGED.sub("(line removed by Brigade)", text)
    return f"{START.format(name=stored_name)}\n{clean}\n{END.format(name=stored_name)}"


def message_with_files(message: str, files: list[tuple[str, str]]) -> str:
    """The typed message followed by each (stored name, text) document."""
    parts = [message.strip()] if message.strip() else []
    parts += [wrap(name, text) for name, text in files]
    return "\n\n".join(parts)


def split_files(text: str) -> tuple[str, tuple[str, ...]]:
    """The typed part of a message and the stored names of the files attached to it."""
    names = tuple(m["name"] for m in BLOCK.finditer(text))
    return BLOCK.sub("", text).strip(), names
