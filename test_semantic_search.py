import asyncio

from app.retrieval.semantic_search import semantic_search


async def main():
    queries = [
        "Who are the characters in this story?",
        "Tell me about someone's childhood or upbringing.",
        "What species do the characters belong to?",
    ]

    for query in queries:
        print(f"\n{'=' * 60}")
        print(f"QUERY: {query}")
        print("=" * 60)

        results = await semantic_search(query, limit=3)

        for result in results:
            print(f"\nFile: {result['file']}")
            print(f"Chunk: {result['chunk_index']}")
            print(f"Similarity: {result['score']:.4f}")
            print(f"Content: {result['content'][:250]}...")


if __name__ == "__main__":
    asyncio.run(main())
