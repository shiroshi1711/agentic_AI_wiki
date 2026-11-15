import asyncio

from app.llm.query_rewriter import rewrite_lore_query


async def main():
    history = [
        {
            "role": "user",
            "content": "Who raised Prince Arven?",
        },
        {
            "role": "assistant",
            "content": "His grandmother raised him.",
        },
    ]

    question = "What happened to her?"

    rewritten = await rewrite_lore_query(
        question,
        history=history,
    )

    print("Original:", question)
    print("Rewritten:", rewritten)


if __name__ == "__main__":
    asyncio.run(main())
