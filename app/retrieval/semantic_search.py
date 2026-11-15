import json
import math

from app.llm.embeddings import generate_embeddings
from app.storage.database import get_connection, initialize_database


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    if len(vector_a) != len(vector_b):
        raise ValueError("Embedding dimensions do not match.")

    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))

    magnitude_a = math.sqrt(sum(a * a for a in vector_a))
    magnitude_b = math.sqrt(sum(b * b for b in vector_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


async def semantic_search(
    query: str,
    limit: int = 5,
) -> list[dict]:
    query = query.strip()

    if not query or limit <= 0:
        return []

    initialize_database()

    # Convert the question into an embedding.
    query_embedding = (await generate_embeddings(
        [query],
        is_query=True,
    ))[0]

    # Load stored chunk embeddings.
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT path, chunk_index, content, embedding_json
            FROM note_chunks
            """
        ).fetchall()

    results = []

    for row in rows:
        document_embedding = json.loads(row["embedding_json"])

        score = cosine_similarity(
            query_embedding,
            document_embedding,
        )

        results.append({
            "file": row["path"],
            "chunk_index": row["chunk_index"],
            "content": row["content"],
            "score": score,
        })

    results.sort(key=lambda item: item["score"], reverse=True)

    return results[:limit]
