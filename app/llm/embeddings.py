import aiohttp

from app.config.settings import get_settings


async def generate_embeddings(
    texts: list[str],
    is_query: bool = False,
) -> list[list[float]]:
    if not texts:
        return []

    settings = get_settings()
    model = settings.embedding_model

    prefix = "search_query: " if is_query else "search_document: "
    inputs = [prefix + text for text in texts]

    payload = {
        "model": model,
        "input": inputs,
    }

    timeout = aiohttp.ClientTimeout(total=120)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{settings.ollama_url}/api/embed",
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()

    embeddings = data.get("embeddings")

    if not embeddings or len(embeddings) != len(texts):
        raise RuntimeError("Ollama returned an unexpected embedding response.")

    return embeddings
