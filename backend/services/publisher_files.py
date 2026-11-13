"""Documents attached to a Publisher message: checked and read before the agent runs."""

from pathlib import Path

from backend.services.publisher_types import PublisherError, Upload
from core.files import uploads
from core.files.extract import FileRejected, extract_text
from pipeline.publisher.chat import MAX_MESSAGE_CHARS

MAX_FILES = 5  # per message


def prepare_files(message: str, files: list[Upload], already: int) -> list[tuple[str, str, bytes]]:
    """(stored name, text, original bytes) of each attached file, read before the agent
    runs, so a bad file is refused without spending a turn."""
    if len(files) > MAX_FILES:
        raise PublisherError(f"At most {MAX_FILES} files can be attached to one message.")
    try:
        texts = [extract_text(f.name, f.data) for f in files]
    except FileRejected as exc:
        raise PublisherError(str(exc)) from None
    if len(message) + sum(len(t) for t in texts) > MAX_MESSAGE_CHARS:
        raise PublisherError("The attached documents are too long together; send fewer.")
    names = uploads.stored_names([f.name for f in files], already)
    return [(n, t, f.data) for n, t, f in zip(names, texts, files, strict=True)]


def save_files(uploads_dir: Path, chat_id: int, prepared: list[tuple[str, str, bytes]]) -> None:
    for stored_name, _text, data in prepared:
        uploads.save(uploads_dir, chat_id, stored_name, data)
