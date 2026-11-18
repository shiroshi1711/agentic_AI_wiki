import re
from app.storage.database import (
    get_connection,
    initialize_database,
)

# Everyday words that appear in almost every note and in every question.
# Searching for them only adds noise ("what is the Sundering" should be
# about "Sundering", not about "what", "is" and "the").
STOP_WORDS = {
    # English
    "a", "an", "the", "of", "to", "in", "on", "at", "for", "from", "by",
    "with", "and", "or", "is", "are", "was", "were", "be", "been", "it",
    "this", "that", "these", "those", "what", "who", "whom", "why", "how",
    "when", "where", "which", "do", "does", "did", "me", "my", "i", "you",
    "tell", "explain", "describe", "about", "happened", "please", "can",
    "could", "would", "give", "show", "write", "summarize", "summary",
    # Indonesian
    "yang", "dan", "di", "ke", "dari", "itu", "ini", "apa", "siapa",
    "kenapa", "mengapa", "bagaimana", "kapan", "dimana", "jelaskan",
    "ceritakan", "tentang", "adalah", "dengan", "untuk", "pada", "saya",
}


def search_vault(query: str, limit: int = 5) -> list[dict]:
    query = query.strip()

    if not query:
        return []

    initialize_database()

    terms = re.findall(r"\w+", query, flags=re.UNICODE)
    if not terms:
        return []

    # Keep the meaningful words. If the question has only filler words,
    # fall back to all of them so we never search for nothing.
    meaningful = [t for t in terms if t.casefold() not in STOP_WORDS]
    terms = meaningful or terms

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
                bm25(notes_fts, 2.0, 8.0, 1.0) AS score
            FROM notes_fts
            WHERE notes_fts MATCH ?
            ORDER BY score  -- columns: path x2, title x8, content x1
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
