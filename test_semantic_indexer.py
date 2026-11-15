import asyncio

from app.retrieval.semantic_indexer import index_vault_semantic
from app.storage.database import get_connection


async def main():
    count = await index_vault_semantic()

    print(f"\nSuccessfully indexed {count} chunks.")

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT path, chunk_index, content, embedding_json
            FROM note_chunks
            LIMIT 3
            """
        ).fetchall()

    print("\nSample stored chunks:")

    for row in rows:
        print(f"\nFile: {row['path']}")
        print(f"Chunk: {row['chunk_index']}")
        print(f"Content: {row['content'][:150]}...")
        print(f"Embedding length: {len(row['embedding_json'])} characters")


if __name__ == "__main__":
    asyncio.run(main())
