from app.storage.database import (
    get_connection,
    initialize_database,
)


def initialize_memory():
    initialize_database()

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (
                    role IN ('user', 'assistant')
                ),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_history
            ON conversation_messages (
                chat_id,
                user_id,
                id
            )
        """)


def save_message(
    chat_id: int,
    user_id: int,
    role: str,
    content: str,
):
    if role not in ("user", "assistant"):
        raise ValueError("Invalid message role.")

    initialize_memory()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO conversation_messages (
                chat_id,
                user_id,
                role,
                content
            )
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, user_id, role, content),
        )


def get_history(
    chat_id: int,
    user_id: int,
    limit: int = 10,
) -> list[dict]:

    initialize_memory()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT role, content
            FROM conversation_messages
            WHERE chat_id = ? AND user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, user_id, limit),
        ).fetchall()

    # Reverse so the oldest message comes first.
    return [
        {
            "role": row["role"],
            "content": row["content"],
        }
        for row in reversed(rows)
    ]


def clear_history(chat_id: int, user_id: int):
    initialize_memory()

    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM conversation_messages
            WHERE chat_id = ? AND user_id = ?
            """,
            (chat_id, user_id),
        )
