import asyncio

from app.llm.embeddings import generate_embeddings


async def main():
    texts = [
        "The prince was raised by his grandmother.",
        "The kingdom was founded after a great war.",
    ]

    embeddings = await generate_embeddings(texts)

    print("Number of embeddings:", len(embeddings))
    print("Dimensions:", len(embeddings[0]))
    print("First five values:", embeddings[0][:5])


if __name__ == "__main__":
    asyncio.run(main())
