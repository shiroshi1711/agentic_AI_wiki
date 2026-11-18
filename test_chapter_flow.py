"""
Tests chapter writing end-to-end with a FAKE model (no Ollama, no Telegram).

Run:  python test_chapter_flow.py
"""
import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import web

SANDBOX = Path(tempfile.mkdtemp(prefix="ella-test-"))
VAULT = SANDBOX / "vault"
(VAULT / "Story Building" / "Chapters").mkdir(parents=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(SANDBOX / "home")
os.environ["VAULT_PATH"] = str(VAULT)
PORT = 18435
os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{PORT}"

from app.agent import tool_registry
from app.agent.loop import run_agent
from app.bot import handlers
from app.storage.database import get_pending_change, get_pending_changes, initialize_database
from app.tools.preview import split_for_telegram
from app.writing import chapters
from app.writing.chapters import (
    chapters_folder, get_story_so_far, is_chapter_path, parse_chapter_output,
    safe_chapter_title, unique_chapter_path,
)

initialize_database()
CHAT, USER = 3, 4

# The real search needs embeddings from Ollama; use a stand-in lore search.
async def fake_lore(query, max_notes=4, max_total_chars=16000):
    return "--- SOURCE: Lore/Aria.md ---\nAria is a royal physician from the Northern Kingdom.", ["Lore/Aria.md"]
chapters.retrieve_context = fake_lore

CHAPTER_ONE = "Lumiere rode north. " * 30
REPLY_1 = f"<think>planning</think># Ignore Me\n\n{CHAPTER_ONE}\n{chapters.NOTES_MARKER}\n- Invented: the inn is called The Gull"
REPLY_2 = f"{'Lumiere rode north, darker now. ' * 30}\n{chapters.NOTES_MARKER}\n- None"

requests_seen, SCRIPT = [], []


async def fake_chat(request):
    body = await request.json()
    requests_seen.append(body)
    return web.json_response(SCRIPT.pop(0))


def reply(text):
    return {"message": {"role": "assistant", "content": text}}


def tool_call(name, arguments):
    return {"message": {"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}}


def check(label):
    print("OK  ", label)


async def main():
    app = web.Application()
    app.router.add_post("/api/chat", fake_chat)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()

    # ---- 1. small pure helpers -----------------------------------------
    long_text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(40))
    pieces = split_for_telegram(long_text)
    assert all(len(p) <= 3800 for p in pieces) and len(pieces) > 1
    assert " ".join(" ".join(pieces).split()) == " ".join(long_text.split())
    check(f"long draft splits into {len(pieces)} Telegram-sized pieces, nothing lost")

    assert safe_chapter_title('A/B: "Return"? [x]#') == "A B Return x"
    assert safe_chapter_title("   ") == "Untitled Chapter"
    assert chapters_folder() == "Story Building/Chapters"
    assert is_chapter_path("Story Building/Chapters/X.md")
    assert not is_chapter_path("Story Building/Characters/X.md")
    assert not is_chapter_path("Story Building/ChaptersExtra/X.md")
    check("title cleaning and chapter-folder detection")

    folder = VAULT / "Story Building" / "Chapters"
    (folder / "Chapter 2.md").write_text("old two", encoding="utf-8")
    (folder / "Chapter 10.md").write_text("start " + "x" * 5000 + " THE-END-OF-TEN", encoding="utf-8")
    story = get_story_so_far()
    assert "THE-END-OF-TEN" in story and story.index("Chapter 2") < story.index("Chapter 10")
    (folder / "Return.md").write_text("exists", encoding="utf-8")
    assert unique_chapter_path("Return") == "Story Building/Chapters/Return (2).md"
    (folder / "Return.md").unlink()  # test helper file: remove so it is not "the latest chapter"
    check("story-so-far uses the highest chapter number (10 after 2); duplicate titles get '(2)'")

    chapter, notes = parse_chapter_output(REPLY_1)
    assert chapter.startswith("Lumiere rode north.") and "The Gull" in notes
    try:
        parse_chapter_output("too short")
    except ValueError:
        check("reply parsed: <think> and stray title removed, notes split off; tiny reply refused")

    # ---- 2. drafting through the agent loop ------------------------------
    SCRIPT[:] = [
        tool_call("draft_chapter", {"title": "The Return", "instructions": "Lumiere returns after the war."}),
        reply(REPLY_1),                                   # the chapter writer
        reply("The draft is ready. Note: the inn is called The Gull."),
    ]
    started = datetime.now(timezone.utc).isoformat()
    answer = await run_agent("Write a chapter where Lumiere returns", chat_id=CHAT, user_id=USER)
    assert "draft is ready" in answer

    writer_request = requests_seen[-2]
    writer_prompt = writer_request["messages"][-1]["content"]
    assert "Aria is a royal physician" in writer_prompt          # lore
    assert "THE-END-OF-TEN" in writer_prompt                     # continuity from last chapter
    assert "Lumiere returns after the war." in writer_prompt     # author's request
    assert writer_request["options"]["num_predict"] == 3500
    assert "tools" not in writer_request                         # plain prose, no tool JSON
    check("writer got lore + end of previous chapter + the request; token cap set; no tools")

    tool_reply = json.loads(requests_seen[-1]["messages"][-1]["content"])
    assert "Lumiere rode north" not in json.dumps(tool_reply)    # chapter text not fed back to the model
    assert "The Gull" in tool_reply["continuity_notes"] and tool_reply["word_count"] >= 60
    check("model is told word count + continuity notes, not the whole chapter")

    pending = get_pending_changes(CHAT, USER, started)
    assert len(pending) == 1
    draft = pending[0]
    assert draft["note_path"] == "Story Building/Chapters/The Return.md"
    assert draft["content"].startswith("# The Return\n\nLumiere rode north.")
    assert "Ignore Me" not in draft["content"] and "CONTINUITY" not in draft["content"]
    assert not (folder / "The Return.md").exists()
    hours = (datetime.fromisoformat(draft["expires_at"]) - datetime.now(timezone.utc)) / timedelta(hours=1)
    assert 23 < hours <= 24
    check("proposal saved: right path/title, no notes inside, 24h expiry, vault untouched")

    # ---- 3. revising ------------------------------------------------------
    SCRIPT[:] = [
        tool_call("revise_chapter", {"feedback": "Make it darker."}),
        reply(REPLY_2),
        reply("I rewrote it darker."),
    ]
    await run_agent("make it darker", chat_id=CHAT, user_id=USER)
    revise_prompt = requests_seen[-2]["messages"][-1]["content"]
    assert "CURRENT DRAFT" in revise_prompt and "Lumiere rode north." in revise_prompt
    assert "Make it darker." in revise_prompt and "# The Return" not in revise_prompt

    assert get_pending_change(draft["proposal_id"])["status"] == "rejected"
    pending = get_pending_changes(CHAT, USER, started)
    assert len(pending) == 1 and pending[0]["proposal_id"] != draft["proposal_id"]
    revised = pending[0]
    assert revised["content"].startswith("# The Return\n\nLumiere rode north, darker now.")
    assert revised["note_path"] == draft["note_path"]
    check("revision: old draft replaced (rejected), new draft keeps title + path, prompt had draft + feedback")

    try:
        await tool_registry.revise_chapter("x", chat_id=999, user_id=999)
    except ValueError as error:
        assert "No chapter draft" in str(error)
        check("revise with nothing waiting -> clear error")

    # ---- 4. Telegram: whole draft is shown, then buttons -----------------
    big = revised["content"] + "\n\n" + "\n\n".join("More story. " * 60 for _ in range(15))
    handlers_message = SimpleNamespace(answer=AsyncMock())
    from app.storage.database import get_connection
    with get_connection() as c:
        c.execute("UPDATE pending_changes SET content=? WHERE proposal_id=?", (big, revised["proposal_id"]))
    await handlers.send_pending_proposals(handlers_message, CHAT, USER, started)
    calls = handlers_message.answer.call_args_list
    assert len(calls) >= 3
    assert all(len(c.args[0]) <= 4096 for c in calls)
    assert "reply_markup" not in calls[0].kwargs and calls[-1].kwargs["reply_markup"] is not None
    assert "just tell me what to change" in calls[-1].args[0]
    check(f"chapter shown in {len(calls) - 1} text pieces + 1 button message, all under Telegram's limit")

    # ---- 5. approve saves it into the chapters folder ---------------------
    async def no_index():
        pass
    handlers.rebuild_indexes = no_index
    callback = SimpleNamespace(
        data=f"approve:{revised['proposal_id']}",
        from_user=SimpleNamespace(id=USER),
        message=SimpleNamespace(chat=SimpleNamespace(id=CHAT), edit_text=AsyncMock()),
        answer=AsyncMock(),
    )
    await handlers.approve_proposal(callback)
    saved = (folder / "The Return.md").read_text(encoding="utf-8")
    assert saved == big
    check("approve: chapter saved at Story Building/Chapters/The Return.md")

    await runner.cleanup()
    print("\nALL CHAPTER-FLOW TESTS PASSED")


asyncio.run(main())
