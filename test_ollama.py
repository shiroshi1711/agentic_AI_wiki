import asyncio

from app.llm.ollama_provider import generate_response


async def main():
    print("Connecting to local AI...")

    answer = await generate_response(
        "Explain what a knowledge management system is, in simple terms."
    )

    print("\nQWEN'S RESPONSE:\n")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
