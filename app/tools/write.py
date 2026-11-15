import os
import shutil
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.config.settings import get_settings


MAX_NOTE_SIZE = 1_000_000

BACKUP_DIR = (
    Path.home()
    / ".local"
    / "share"
    / "elarion-ai-wiki"
    / "backups"
)


def _validate_note_path(note_path: str) -> tuple[Path, Path]:
    """Validate a relative Markdown path inside the Obsidian vault."""

    if not note_path or "\x00" in note_path:
        raise ValueError("A valid note path is required.")

    relative_path = Path(note_path)

    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("Invalid note path.")

    if any(part.startswith(".") for part in relative_path.parts):
        raise ValueError("Hidden folders and files are not allowed.")

    if relative_path.suffix.lower() != ".md":
        raise ValueError("Only Markdown files are supported.")

    vault_path = get_settings().vault_path.resolve()
    target_path = vault_path / relative_path

    resolved_path = target_path.resolve()

    if not resolved_path.is_relative_to(vault_path):
        raise ValueError("The path is outside the Obsidian vault.")

    return vault_path, target_path


def _validate_content(content: str) -> None:
    if not isinstance(content, str):
        raise ValueError("Note content must be text.")

    if len(content.encode("utf-8")) > MAX_NOTE_SIZE:
        raise ValueError("Note exceeds the 1 MB size limit.")


def get_note_hash(note_path: str) -> str:
    """Return a SHA-256 fingerprint of an existing note."""

    vault_path, target_path = _validate_note_path(note_path)

    if target_path.is_symlink():
        raise ValueError("Symbolic links are not allowed.")

    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note does not exist: {note_path}"
        )

    if target_path.stat().st_size > MAX_NOTE_SIZE:
        raise ValueError("Note is too large.")

    content = target_path.read_bytes()

    return hashlib.sha256(content).hexdigest()


def _create_backup(
    vault_path: Path,
    note_path: Path,
) -> Path:
    """Create a timestamped backup outside the Obsidian vault."""

    relative_path = note_path.relative_to(vault_path)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d-%H%M%S-%f"
    )

    backup_path = (
        BACKUP_DIR
        / timestamp
        / relative_path
    )

    backup_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(note_path, backup_path)

    return backup_path


def create_note(note_path: str, content: str) -> str:
    """Create a new Markdown note without overwriting existing files."""

    _validate_content(content)

    vault_path, target_path = _validate_note_path(note_path)

    target_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Recheck after creating parent directories.
    if target_path.is_symlink():
        raise ValueError("Symbolic links are not allowed.")

    if not target_path.resolve().is_relative_to(vault_path):
        raise ValueError("The path is outside the Obsidian vault.")

    if target_path.exists():
        raise FileExistsError(
            f"A note already exists at: {note_path}"
        )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)

        # Atomic creation that refuses to overwrite an existing note.
        os.link(temporary_path, target_path)

        return f"Created note: {note_path}"

    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def update_note(note_path: str, content: str) -> str:
    """Back up and replace an existing Markdown note."""

    _validate_content(content)

    vault_path, target_path = _validate_note_path(note_path)

    if target_path.is_symlink():
        raise ValueError("Symbolic links are not allowed.")

    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note does not exist: {note_path}"
        )

    # Preserve the original before changing anything.
    backup_path = _create_backup(
        vault_path,
        target_path,
    )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)

        os.replace(temporary_path, target_path)

        return (
            f"Updated note: {note_path}\n"
            f"Backup saved at: {backup_path}"
        )

    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
def update_note(
    note_path: str,
    content: str,
    expected_hash: str | None = None,
) -> str:
    """Back up and replace an existing Markdown note."""

    _validate_content(content)

    vault_path, target_path = _validate_note_path(note_path)

    if target_path.is_symlink():
        raise ValueError("Symbolic links are not allowed.")

    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note does not exist: {note_path}"
        )

    # Check that the note hasn't changed since the proposal.
    if expected_hash is not None:
        current_hash = get_note_hash(note_path)

        if current_hash != expected_hash:
            raise ValueError(
                "This note has changed since the proposal was created. "
                "Please review the latest version before approving."
            )

    # Preserve the original before changing anything.
    backup_path = _create_backup(
        vault_path,
        target_path,
    )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)

        os.replace(temporary_path, target_path)

        return (
            f"Updated note: {note_path}\n"
            f"Backup saved at: {backup_path}"
        )

    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
