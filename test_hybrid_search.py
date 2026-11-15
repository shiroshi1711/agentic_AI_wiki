import asyncio

from app.retrieval.hybrid_search import hybrid_search


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

        results = await hybrid_search(query, limit=5)

        for result in results:
            print(f"\nFile: {result['file']}")
            print(f"Combined score: {result['score']:.5f}")
            print(f"Matched by: {', '.join(result['sources'])}")


if __name__ == "__main__":
    asyncio.run(main())
