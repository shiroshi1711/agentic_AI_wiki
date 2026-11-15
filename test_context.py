import asyncio

from app.retrieval.context import retrieve_context


async def main():
    queries = [
        "Who raised the young prince?",
        "What do we know about the Astravelle family?",
        "Which characters are connected to the Northern Sea War?",
    ]

    for query in queries:
        print(f"\n{'=' * 60}")
        print(f"QUERY: {query}")
        print("=" * 60)

        context, sources = await retrieve_context(query)

        print("\nSOURCES:")
        for source in sources:
            print(f"- {source}")

        print("\nCONTEXT:")
        print(context[:1500])


if __name__ == "__main__":
    asyncio.run(main())
