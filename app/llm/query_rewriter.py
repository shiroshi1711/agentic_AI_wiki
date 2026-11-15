from app.llm.ollama_provider import generate_response


SYSTEM_PROMPT = """
You rewrite follow-up questions into standalone search queries.

Rules:
1. Use conversation history to resolve pronouns and references.
2. Preserve the user's original intent.
3. Do not answer the question.
4. Do not add facts that are not established in the conversation.
5. If a reference is unclear, preserve the original question.
6. Return only the rewritten question.
7. Do not include explanations, labels, or quotation marks.
"""


async def rewrite_lore_query(
    question: str,
    history: list[dict] | None = None,
) -> str:
    if not history:
        return question

    rewritten = await generate_response(
        prompt=(
            "Rewrite this latest question as a standalone search query:\n\n"
            f"{question}"
        ),
        system_prompt=SYSTEM_PROMPT,
        history=history,
    )

    rewritten = rewritten.strip().strip('"').strip("'")

    if not rewritten:
        return question

    return rewritten
