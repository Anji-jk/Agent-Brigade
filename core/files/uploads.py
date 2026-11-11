"""The original uploaded files, kept in <BRIGADE_DATA_DIR>/uploads/<chat id>/.

Each file is stored as '<nn>-<name>' (01-requirements.docx, 02-...), numbered per chat, so two
uploads with the same name never overwrite each other and every file can be named exactly.
"""

import re
from dataclasses import dataclass
from pathlib import Path, PurePath

UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")
STORED = re.compile(r"^[0-9]{2,4}-[A-Za-z0-9._ -]+$")
MAX_NAME_CHARS = 100


@dataclass(frozen=True)
class StoredFile:
    stored_name: str  # 01-requirements.docx
    name: str  # requirements.docx
    size: int


def safe_name(name: str) -> str:
    """A file name without folders or characters Windows and shells trip over."""
    base = PurePath(name.replace("\\", "/")).name
    stem, suffix = PurePath(base).stem, PurePath(base).suffix.lower()
    stem = UNSAFE.sub("_", stem).strip(" ._") or "file"
    return stem[: MAX_NAME_CHARS - len(suffix)] + suffix


def chat_folder(uploads_dir: Path, chat_id: int) -> Path:
    return uploads_dir / f"PUB-{chat_id:06d}"


def stored_names(names: list[str], already: int = 0) -> list[str]:
    """The names files will be stored under, numbered after the `already` stored ones."""
    return [f"{already + n:02d}-{safe_name(name)}" for n, name in enumerate(names, 1)]


def list_files(uploads_dir: Path, chat_id: int) -> list[StoredFile]:
    folder = chat_folder(uploads_dir, chat_id)
    if not folder.is_dir():
        return []
    return [
        StoredFile(p.name, p.name.split("-", 1)[1], p.stat().st_size)
        for p in sorted(folder.iterdir())
        if p.is_file() and STORED.match(p.name)
    ]


def save(uploads_dir: Path, chat_id: int, stored_name: str, data: bytes) -> Path:
    if not STORED.match(stored_name):
        raise ValueError(f"'{stored_name}' is not a stored file name.")
    folder = chat_folder(uploads_dir, chat_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / stored_name
    path.write_bytes(data)
    return path


def find(uploads_dir: Path, chat_id: int, stored_name: str) -> Path | None:
    """The stored file, or None. Only names the folder actually holds are ever opened."""
    for item in list_files(uploads_dir, chat_id):
        if item.stored_name == stored_name:
            return chat_folder(uploads_dir, chat_id) / item.stored_name
    return None
