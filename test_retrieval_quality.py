"""
Does Ella find the RIGHT part of a long EVENT note (not just character notes)?

Uses a fake embedding server (words -> numbers), so no Ollama is needed.

Run:  python test_retrieval_quality.py
"""
import asyncio
import math
import os
import re
import tempfile
import zlib
from pathlib import Path

from aiohttp import web

SANDBOX = Path(tempfile.mkdtemp(prefix="ella-test-"))
VAULT = SANDBOX / "vault"
(VAULT / "Events").mkdir(parents=True)
(VAULT / "Characters").mkdir(parents=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(SANDBOX / "home")
os.environ["VAULT_PATH"] = str(VAULT)
PORT = 18436
os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{PORT}"

from app.retrieval.context import retrieve_context
from app.retrieval.indexer import index_vault
from app.retrieval.semantic_indexer import index_vault_semantic
from app.retrieval.semantic_search import semantic_search
from app.storage.database import initialize_database
from app.tools.search import search_vault

# ---------------------------------------------------------------- fixtures
FILLER = "The wind crossed the empty plains and nobody spoke of it. " * 24  # ~1400 chars

SUNDERING = "# The Sundering\n\n" + "\n\n".join([
    "The Sundering was the night the old kingdom broke apart. " + FILLER,
    "First came the drought, then the riots in the river towns. " + FILLER,
    "Queen Veyra closed the gates and refused every petition. " + FILLER,
    "On the second night the granaries burned. " + FILLER,
    "On the third night the generals turned on the throne. " + FILLER,
    "The council fled east after the third night, carrying the royal seal. " + FILLER,
    "In the years after, the survivors rebuilt the northern towns by hand, "
    "and the old order never met again. " + FILLER,
])
assert len(SUNDERING) > 6000
assert SUNDERING.index("council fled east") > 3500
assert SUNDERING.index("survivors rebuilt") > 6000   # beyond the old 6000-char cut-off

NOTES = {
    "Events/The Sundering.md": SUNDERING,
    "Events/Harvest Festival.md": (
        "The Harvest Festival is held every autumn. The survivors' dance, the "
        "consequences of the wine, and the festival songs are loved by all. " * 6
    ),
    "Characters/Aria.md": "Fullname: Aria Vale\nAria is a royal physician. She mentioned the Sundering once.",
    "Events/Trade Routes.md": "Trade routes cross the plains. Merchants pay tolls at the river towns. " * 8,
}
for relative, text in NOTES.items():
    (VAULT / relative).write_text(text, encoding="utf-8")


# ------------------------------------------------- fake embedding server
def embed(text: str, dims: int = 512) -> list[float]:
    vector = [0.0] * dims
    for word in re.findall(r"\w+", text.lower()):
        vector[zlib.crc32(word.encode()) % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


EMBED_INPUTS = []  # everything the indexer asked us to embed


async def fake_embed(request):
    body = await request.json()
    EMBED_INPUTS.extend(body["input"])
    return web.json_response({"embeddings": [embed(t) for t in body["input"]]})


def check(label):
    print("OK  ", label)


async def main():
    app = web.Application()
    app.router.add_post("/api/embed", fake_embed)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()

    initialize_database()
    index_vault()
    await index_vault_semantic()

    # 1. Keyword search: question words must not drown the event name,
    #    and a note TITLED like the event must beat a note that mentions it once.
    hits = search_vault("what is the Sundering")
    assert hits[0]["file"] == "Events/The Sundering.md", [h["file"] for h in hits]
    check("keyword search: 'what is the Sundering' -> the Sundering note first")

    # 2. Meaning search: every chunk is embedded TOGETHER WITH its note's title,
    #    so a chunk from deep inside the event can be tied to the event's name.
    #    (A word-counting fake can't judge real embedding quality, so we check
    #    the mechanism: what the indexer actually sends to the embedding model.)
    sundering_inputs = [t for t in EMBED_INPUTS if "survivors rebuilt" in t or "council fled east" in t]
    assert sundering_inputs, "deep chunks were never embedded"
    assert all("Note: The Sundering (folder: Events)" in t for t in sundering_inputs)
    check("every chunk is embedded together with its note's title and folder")

    from app.retrieval.hybrid_search import hybrid_search
    ranked = await hybrid_search("consequences of the Sundering for the survivors", limit=3)
    assert ranked[0]["file"] == "Events/The Sundering.md", [r["file"] for r in ranked]
    assert ranked[0]["chunks"], "matching passages were not kept"
    check("combined search ranks the event note first and keeps its matching passages")

    # 3. Context for a deep question must contain the deep passage, not just
    #    the first 6000 characters of the note.
    context, sources = await retrieve_context("why did the council flee east after the third night")
    assert "council fled east after the third night" in context
    assert "Events/The Sundering.md" in sources
    check("context includes the passage that answers a deep question")

    context, sources = await retrieve_context("consequences of the Sundering for the survivors")
    assert "survivors rebuilt the northern towns" in context, "deep ending missing"
    assert "The Sundering was the night the old kingdom broke apart" in context, "intro missing"
    check("long note: intro AND the matching deep passage are both included")

    # 4. Short notes are still included whole.
    context, _ = await retrieve_context("Aria royal physician")
    assert "Aria is a royal physician" in context
    check("short notes are still included whole")

    await runner.cleanup()
    print("\nALL RETRIEVAL-QUALITY TESTS PASSED")


asyncio.run(main())
