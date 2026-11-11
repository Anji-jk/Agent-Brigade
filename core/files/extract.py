"""The plain text of an uploaded requirement document: .txt, .md, .docx or .pdf."""

import io
from pathlib import PurePath

MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
MAX_TEXT_CHARS = 150_000  # what one document may add to a message
SUFFIXES = (".txt", ".md", ".docx", ".pdf")


class FileRejected(ValueError):
    """The file cannot be used; the message says why, for the person who uploaded it."""


def check_upload(name: str, size: int) -> str:
    """The file's suffix, if Brigade accepts files of this name and size."""
    suffix = PurePath(name).suffix.lower()
    if suffix not in SUFFIXES:
        raise FileRejected(f"{name}: only {', '.join(SUFFIXES)} files can be attached.")
    if size == 0:
        raise FileRejected(f"{name} is empty.")
    if size > MAX_BYTES:
        raise FileRejected(f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    return suffix


def extract_text(name: str, data: bytes) -> str:
    """The document's text, or FileRejected with the reason."""
    suffix = check_upload(name, len(data))
    try:
        if suffix in (".txt", ".md"):
            text = _plain(data)
        elif suffix == ".docx":
            text = _docx(data)
        else:
            text = _pdf(name, data)
    except FileRejected:
        raise
    except Exception as exc:  # a damaged or mislabelled file: say so instead of failing
        raise FileRejected(f"{name} could not be read as a {suffix} file.") from exc
    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()
    if not text:
        raise FileRejected(f"{name} has no text.")
    if len(text) > MAX_TEXT_CHARS:
        raise FileRejected(
            f"{name} has more than {MAX_TEXT_CHARS:,} characters of text; split it into parts."
        )
    return text


def _plain(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")  # files saved by older Windows tools


def _docx(data: bytes) -> str:
    from importlib import import_module

    Document = import_module("docx").Document

    document = Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)


def _pdf(name: str, data: bytes) -> str:
    from importlib import import_module

    PdfReader = import_module("pypdf").PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise FileRejected(f"{name} is password-protected.")
    text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise FileRejected(f"{name} has no text layer; it is probably a scan.")
    return text
