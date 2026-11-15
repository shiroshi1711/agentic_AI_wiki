import aiohttp

from app.config.settings import get_settings


async def generate_response(
    prompt: str,
    system_prompt: str = (
        "You are a helpful AI assistant. "
        "Answer accurately and clearly."
    ),
    history: list[dict] | None = None,
) -> str:

    settings = get_settings()
    model = settings.llm_model or "qwen3:4b"

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    if history:
        for item in history:
            if item["role"] in ("user", "assistant"):
                messages.append({
                    "role": item["role"],
                    "content": item["content"],
                })

    messages.append({
        "role": "user",
        "content": prompt,
    })

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            "http://127.0.0.1:11434/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()

    return data["message"]["content"]
