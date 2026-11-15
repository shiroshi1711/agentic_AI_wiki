from pathlib import Path

from app.config.settings import get_settings
from app.storage.database import (
    get_connection,
    initialize_database,
)


def index_vault() -> int:
    vault = get_settings().vault_path.resolve()

    if not vault.is_dir():
        raise FileNotFoundError(f"Vault not found: {vault}")

    initialize_database()

    indexed = []

    for file_path in vault.rglob("*.md"):
        relative = file_path.relative_to(vault)

        if any(
            part.startswith(".")
            for part in relative.parts
        ):
            continue

        resolved = file_path.resolve()

        if not resolved.is_relative_to(vault):
            continue

        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        indexed.append((
            relative.as_posix(),
            file_path.stem,
            content,
        ))

    # Replace the index in one transaction.
    # If indexing fails, the previous index remains intact.
    with get_connection() as connection:
        connection.execute("DELETE FROM notes_fts")
        connection.execute("DELETE FROM notes")

        connection.executemany(
            """
            INSERT INTO notes (path, title, content)
            VALUES (?, ?, ?)
            """,
            indexed,
        )

        connection.execute("""
            INSERT INTO notes_fts (path, title, content)
            SELECT path, title, content FROM notes
        """)

    return len(indexed)
