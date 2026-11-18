import re

import aiohttp

from app.config.settings import get_settings


_THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """
    Remove Qwen3's <think>...</think> "inner monologue" from a reply.

    Some Ollama versions put the model's private thinking inside the
    answer. The user should only see the final answer.
    """
    return _THINK_PATTERN.sub("", text or "").strip()


def build_chat_payload(
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Build the JSON body we send to Ollama's /api/chat."""
    settings = get_settings()

    payload = {
        "model": settings.llm_model or "qwen3:4b",
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": settings.llm_num_ctx},
    }

    if max_tokens:
        # num_predict = the most tokens the model may write in this reply.
        payload["options"]["num_predict"] = max_tokens

    if tools:
        payload["tools"] = tools

    return payload


async def generate_response(
    prompt: str,
    system_prompt: str = (
        "You are a helpful AI assistant. "
        "Answer accurately and clearly."
    ),
    history: list[dict] | None = None,
    max_tokens: int | None = None,
    timeout_seconds: int = 600,
) -> str:

    settings = get_settings()

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

    payload = build_chat_payload(messages, max_tokens=max_tokens)

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{settings.ollama_url}/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()

    return strip_thinking(data["message"]["content"])
