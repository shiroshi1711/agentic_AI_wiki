from app.retrieval.hybrid_search import hybrid_search
from app.tools.read import read_note


# A note this short is given to the model whole.
SMALL_NOTE_CHARS = 3500
# For a longer note: its beginning (usually says what the note is about)...
INTRO_CHARS = 1200
# ...plus up to this many of the passages that best matched the question.
MAX_MATCHED_PASSAGES = 3
# A keyword-only match has no passage information: show this much of the top.
FALLBACK_CHARS = 3000
MAX_CHARS_PER_NOTE = 6000


def _build_note_text(content: str, result: dict) -> str:
    if len(content) <= SMALL_NOTE_CHARS:
        return content

    chunks = sorted(
        result.get("chunks", []),
        key=lambda chunk: chunk["score"],
        reverse=True,
    )[:MAX_MATCHED_PASSAGES]

    # Chunk 0 is the start of the note, which the intro already covers.
    chunks = sorted(
        (c for c in chunks if c["chunk_index"] != 0),
        key=lambda chunk: chunk["chunk_index"],
    )

    if not chunks:
        return (
            content[:FALLBACK_CHARS].rstrip()
            + "\n...[excerpt only: this is a long note. "
            "Use explain_note to cover all of it.]"
        )

    parts = ["[beginning of the note]\n" + content[:INTRO_CHARS].strip()]

    for chunk in chunks:
        parts.append(
            f"[passage that matches the question, part {chunk['chunk_index'] + 1}]\n"
            + chunk["content"]
        )

    parts.append(
        "[excerpts only: this is a long note. "
        "Use explain_note to cover all of it.]"
    )

    return "\n\n".join(parts)


async def retrieve_context(
    query: str,
    max_notes: int = 4,
    max_total_chars: int = 16000,
) -> tuple[str, list[str]]:

    results = await hybrid_search(query, limit=max_notes)

    if not results:
        return "", []

    context_parts = []
    sources = []
    remaining = max_total_chars

    for result in results:
        path = result["file"]

        try:
            content = read_note(path)
        except (OSError, ValueError, FileNotFoundError):
            continue

        if not content.strip() or remaining <= 0:
            continue

        text = _build_note_text(content, result)
        text = text[:min(MAX_CHARS_PER_NOTE, remaining)]

        context_parts.append(
            f"--- SOURCE: {path} ---\n{text}"
        )

        sources.append(path)
        remaining -= len(text)

    return "\n\n".join(context_parts), sources
