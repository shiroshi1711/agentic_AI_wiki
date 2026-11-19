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


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Reading helpers used when PREPARING a change (nothing is written here)
# ---------------------------------------------------------------------------

def read_note_with_hash(note_path: str) -> tuple[str, str]:
    """
    Read an existing note ONCE and return (text, fingerprint).

    Both values come from the exact same bytes, so the fingerprint always
    matches the text we are about to edit.
    """

    vault_path, target_path = _validate_note_path(note_path)

    if target_path.is_symlink():
        raise ValueError("Symbolic links are not allowed.")

    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note does not exist: {note_path}"
        )

    if target_path.stat().st_size > MAX_NOTE_SIZE:
        raise ValueError("Note is too large.")

    raw = target_path.read_bytes()

    return (
        raw.decode("utf-8"),
        hashlib.sha256(raw).hexdigest(),
    )


def get_note_hash(note_path: str) -> str:
    """Return a SHA-256 fingerprint of an existing note."""
    return read_note_with_hash(note_path)[1]


def apply_text_edit(content: str, old_text: str, new_text: str) -> str:
    """
    Replace ONE exact piece of text inside a note.

    This is much safer than letting the AI retype a whole note:
    if the AI guesses wrong, we refuse instead of damaging the note.
    """

    if not old_text:
        raise ValueError("old_text must not be empty.")

    if old_text == new_text:
        raise ValueError("old_text and new_text are identical.")

    count = content.count(old_text)

    if count == 0:
        raise ValueError(
            "old_text was not found in the note. "
            "Read the note again and copy the text exactly."
        )

    if count > 1:
        raise ValueError(
            f"old_text appears {count} times in the note. "
            "Include more surrounding text so it matches exactly once."
        )

    return content.replace(old_text, new_text, 1)


def apply_append(content: str, text: str) -> str:
    """Add text to the end of a note (on its own new line)."""

    if not text or not text.strip():
        raise ValueError("There is no text to append.")

    if content and not content.endswith("\n"):
        content += "\n"

    return content + text.rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Writing helpers used ONLY after the user taps Approve
# ---------------------------------------------------------------------------

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
        # newline="" means: write the text exactly as given.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
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
            newline="",
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


def delete_note(note_path: str, expected_hash: str) -> str:
    """
    Delete a note, but only after making a backup copy OUTSIDE the vault.

    Safety order: check the path -> check the note is unchanged since the
    proposal -> copy it to the backup folder -> verify the copy -> delete.
    If any step fails, nothing is deleted.
    """

    vault_path, target_path = _validate_note_path(note_path)

    if target_path.is_symlink():
        raise ValueError("Symbolic links are not allowed.")

    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note does not exist: {note_path}"
        )

    if get_note_hash(note_path) != expected_hash:
        raise ValueError(
            "This note has changed since the deletion was proposed. "
            "Please review it again before deleting."
        )

    backup_path = _create_backup(vault_path, target_path)

    if (
        not backup_path.is_file()
        or backup_path.stat().st_size != target_path.stat().st_size
    ):
        raise RuntimeError(
            "The backup could not be verified, so the note was NOT deleted."
        )

    target_path.unlink()

    return (
        f"Deleted note: {note_path}\n"
        f"Backup saved at: {backup_path}"
    )
