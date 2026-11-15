from app.retrieval.hybrid_search import hybrid_search
from app.tools.read import read_note


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

        content = content[:min(6000, remaining)]

        context_parts.append(
            f"--- SOURCE: {path} ---\n{content}"
        )

        sources.append(path)
        remaining -= len(content)

    return "\n\n".join(context_parts), sources
