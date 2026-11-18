import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4

DB_PATH = (
    Path.home()
    / ".local"
    / "share"
    / "elarion-ai-wiki"
    / "index.sqlite3"
)


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
            USING fts5(path, title, content)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS note_chunks (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                UNIQUE(path, chunk_index)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_note_chunks_path
            ON note_chunks(path)
        """)

	        # Knowledge Graph: entities
        connection.execute("""
            CREATE TABLE IF NOT EXISTS graph_entities (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                entity_type TEXT NOT NULL DEFAULT 'character',
                source_path TEXT,
                has_note INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Knowledge Graph: character attributes
        connection.execute("""
            CREATE TABLE IF NOT EXISTS graph_attributes (
                id INTEGER PRIMARY KEY,
                entity_id INTEGER NOT NULL,
                attribute_name TEXT NOT NULL,
                attribute_value TEXT NOT NULL,
                source_path TEXT NOT NULL,
                FOREIGN KEY (entity_id)
                    REFERENCES graph_entities(id)
                    ON DELETE CASCADE
            )
        """)

        # Knowledge Graph: relationships
        connection.execute("""
            CREATE TABLE IF NOT EXISTS graph_relationships (
                id INTEGER PRIMARY KEY,
                source_entity_id INTEGER NOT NULL,
                target_entity_id INTEGER NOT NULL,
                relationship_type TEXT NOT NULL,
                source_path TEXT NOT NULL,
                FOREIGN KEY (source_entity_id)
                    REFERENCES graph_entities(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (target_entity_id)
                    REFERENCES graph_entities(id)
                    ON DELETE CASCADE
            )
        """)

        # Knowledge Graph: indexes
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_graph_attributes_entity
            ON graph_attributes(entity_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_graph_relationships_source
            ON graph_relationships(source_entity_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_graph_relationships_target
            ON graph_relationships(target_entity_id)
        """)

        
        # Pending note changes: nothing is written to the vault until approved.
        connection.execute("""
            CREATE TABLE IF NOT EXISTS pending_changes (
                proposal_id TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                operation TEXT NOT NULL
                    CHECK (operation IN ('create', 'update')),
                note_path TEXT NOT NULL,
                content TEXT NOT NULL,
                original_hash TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending',
                        'approved',
                        'rejected',
                        'completed',
                        'failed',
                        'expired'
                    )),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        # Index for faster approval lookups
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_changes_status
            ON pending_changes(status)
        """)



def create_pending_change(
    chat_id: int,
    user_id: int,
    operation: str,
    note_path: str,
    content: str,
    original_hash: str | None = None,
    expires_minutes: int = 30,
) -> str:
    """Save a proposed note change without modifying the vault."""

    if operation not in ("create", "update"):
        raise ValueError("Operation must be 'create' or 'update'.")

    proposal_id = str(uuid4())

    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    expires_at = (now + timedelta(minutes=expires_minutes)).isoformat()

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO pending_changes (
                proposal_id,
                chat_id,
                user_id,
                operation,
                note_path,
                content,
                original_hash,
                status,
                created_at,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                proposal_id,
                chat_id,
                user_id,
                operation,
                note_path,
                content,
                original_hash,
                created_at,
                expires_at,
            ),
        )

        connection.commit()
        return proposal_id

    finally:
        connection.close()


def get_pending_change(proposal_id: str):
    """Retrieve a proposal by its ID."""

    connection = get_connection()

    try:
        result = connection.execute(
            """
            SELECT *
            FROM pending_changes
            WHERE proposal_id = ?
            """,
            (proposal_id,),
        ).fetchone()

        return dict(result) if result else None

    finally:
        connection.close()


def update_proposal_status(
    proposal_id: str,
    expected_status: str,
    new_status: str,
) -> bool:
    """Change status only if the proposal is in the expected state."""

    allowed_transitions = {
        ("pending", "approved"),
        ("pending", "rejected"),
        ("pending", "expired"),
        ("approved", "completed"),
        ("approved", "failed"),
    }

    if (expected_status, new_status) not in allowed_transitions:
        raise ValueError("Invalid proposal status transition.")

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            UPDATE pending_changes
            SET status = ?
            WHERE proposal_id = ?
              AND status = ?
            """,
            (new_status, proposal_id, expected_status),
        )

        connection.commit()
        return cursor.rowcount == 1

    finally:
        connection.close()


def expire_pending_changes() -> int:
    """Expire proposals that have passed their deadline."""

    now = datetime.now(timezone.utc).isoformat()

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            UPDATE pending_changes
            SET status = 'expired'
            WHERE status = 'pending'
              AND expires_at <= ?
            """,
            (now,),
        )

        connection.commit()
        return cursor.rowcount

    finally:
        connection.close()


def get_pending_changes(chat_id: int, user_id: int, created_after: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM pending_changes
            WHERE chat_id = ?
              AND user_id = ?
              AND status = 'pending'
              AND created_at >= ?
            ORDER BY created_at ASC
            """,
            (chat_id, user_id, created_after),
        ).fetchall()

    return [dict(row) for row in rows]
