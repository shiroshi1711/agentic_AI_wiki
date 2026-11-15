def chunk_text(
    text: str,
    chunk_size: int =1200,
    overlap: int = 180,
) -> list[str]:
    """Split text into overlapping chunks, preferring natural boundaries."""

    text = text.strip()

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size.")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            # Prefer ending at a paragraph, line, sentence, or word boundary.
            search_start = start + chunk_size // 2

            boundaries = [
                text.rfind("\n\n", search_start, end),
                text.rfind("\n", search_start, end),
                text.rfind(". ", search_start, end),
                text.rfind(" ", search_start, end),
            ]

            best_boundary = max(boundaries)

            if best_boundary > start:
                end = best_boundary + (
                    2 if text[best_boundary:best_boundary + 2] == ". " else 1
                )

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        # Move forward while retaining some context from the previous chunk.
        start = max(start + 1, end - overlap)

    return chunks
