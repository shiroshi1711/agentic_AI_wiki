from pathlib import Path

from app.config.settings import get_settings


def read_note(note_path: str) -> str:
    vault = get_settings().vault_path.resolve()

    relative_path = Path(note_path)

    # Only accept relative Markdown paths
    if relative_path.is_absolute():
        raise ValueError("Absolute paths are not allowed.")

    if ".." in relative_path.parts:
        raise ValueError("Path traversal is not allowed.")

    if any(part.startswith(".") for part in relative_path.parts):
        raise ValueError("Hidden files and folders are not allowed.")

    if relative_path.suffix.lower() != ".md":
        raise ValueError("Only Markdown files can be read.")

    target = (vault / relative_path).resolve()

    # Ensure the resolved path stays inside the vault
    if not target.is_relative_to(vault):
        raise ValueError("Access outside the vault is forbidden.")

    if not target.is_file():
        raise FileNotFoundError("Note not found.")

    if target.stat().st_size > 1_000_000:
        raise ValueError("Note is too large to read.")

    return target.read_text(encoding="utf-8")
