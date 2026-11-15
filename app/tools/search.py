import re
from app.storage.database import (
    get_connection,
    initialize_database,
)

def search_vault(query: str, limit: int = 5) -> list[dict]:
    query = query.strip()

    if not query:
        return []

    initialize_database()

    terms = re.findall(r"\w+", query, flags=re.UNICODE)
    if not terms:
        return []

    safe_query = " OR ".join(
    '"' + term.replace('"', '""') + '"'
    for term in terms
)

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                path,
                title,
                snippet(notes_fts, 2, '', '', ' … ', 20) AS snippet,
                bm25(notes_fts) AS score
            FROM notes_fts
            WHERE notes_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (safe_query, limit),
        ).fetchall()

    return [
        {
            "file": row["path"],
            "title": row["title"],
            "snippet": row["snippet"],
        }
        for row in rows
    ]
