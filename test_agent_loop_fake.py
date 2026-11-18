"""
Tests Ella's agent loop WITHOUT a real model. A tiny fake "Ollama" server
plays the part of Qwen with a fixed script, so we can check that the loop
itself (tool calls, safety, limits) works.

Run:  python test_agent_loop_fake.py
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

from aiohttp import web

SANDBOX = Path(tempfile.mkdtemp(prefix="ella-test-"))
(SANDBOX / "vault").mkdir(parents=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(SANDBOX / "home")
os.environ["VAULT_PATH"] = str(SANDBOX / "vault")
PORT = 18434
os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{PORT}"

(SANDBOX / "vault" / "Lumiere.md").write_text("Occupation: Knight\n", encoding="utf-8")

from app.agent.loop import MAX_TOOL_CALLS, TOOL_SCHEMAS, run_agent
from app.storage.database import get_pending_changes, initialize_database

initialize_database()
requests_seen = []


def tool_call(name, arguments):
    return {"message": {"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}}


def final(text):
    return {"message": {"role": "assistant", "content": text}}


SCRIPT = []  # replies the fake model will give, in order


async def fake_chat(request):
    body = await request.json()
    requests_seen.append(body)
    return web.json_response(SCRIPT.pop(0))


async def main():
    app = web.Application()
    app.router.add_post("/api/chat", fake_chat)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()

    # --- 1. read a note, then edit it. The model tries to FAKE the identity.
    SCRIPT[:] = [
        tool_call("read_note", {"note_path": "Lumiere.md"}),
        tool_call("propose_edit_note", {
            "note_path": "Lumiere.md", "old_text": "Knight", "new_text": "King",
            "chat_id": 999, "user_id": 999, "invented_extra": "x",
        }),
        final("<think>hmm</think>I prepared the change. Please approve it."),
    ]
    started = "2000-01-01T00:00:00"
    answer = await run_agent("Make Lumiere a king", chat_id=11, user_id=22)
    assert answer == "I prepared the change. Please approve it.", answer
    proposals = get_pending_changes(11, 22, started)
    assert len(proposals) == 1 and not get_pending_changes(999, 999, started)
    assert (SANDBOX / "vault" / "Lumiere.md").read_text() == "Occupation: Knight\n"
    tool_replies = [m for m in requests_seen[-1]["messages"] if m["role"] == "tool"]
    assert len(tool_replies) == 2
    assert requests_seen[0]["options"]["num_ctx"] == 8192
    assert len(requests_seen[0]["tools"]) == len(TOOL_SCHEMAS)
    print("OK   read -> propose_edit_note -> answer; identity from Telegram, not from the model;")
    print("     fake extra argument ignored; <think> removed; vault untouched")

    # --- 2. an unknown / unlisted tool is refused, loop continues
    SCRIPT[:] = [
        tool_call("delete_everything", {}),
        tool_call("propose_update_note", {"note_path": "Lumiere.md", "content": "x"}),
        final("Done."),
    ]
    answer = await run_agent("be bad", chat_id=11, user_id=22)
    errors = [m["content"] for m in requests_seen[-1]["messages"] if m["role"] == "tool"]
    assert all("Unknown tool" in e for e in errors) and len(errors) == 2, errors
    print("OK   unknown tool and the removed whole-note rewrite tool are both refused")

    # --- 3. a model that never stops asking for tools is cut off
    SCRIPT[:] = [tool_call("search_notes", {"query": "x"}) for _ in range(MAX_TOOL_CALLS)]
    SCRIPT.append(final("Here is what I found."))
    before = len(requests_seen)
    answer = await run_agent("loop forever", chat_id=11, user_id=22)
    assert answer == "Here is what I found."
    last = requests_seen[-1]
    assert "tools" not in last, "tools must not be offered after the limit"
    assert len(requests_seen) - before == MAX_TOOL_CALLS + 1
    print(f"OK   limit of {MAX_TOOL_CALLS} tool calls enforced; final answer forced without tools")

    # --- 4. empty final answer gives a friendly fallback
    SCRIPT[:] = [final("<think>only thinking</think>")]
    answer = await run_agent("hi")
    assert "couldn't" in answer
    print("OK   empty answer -> friendly fallback")

    await runner.cleanup()
    print("\nALL AGENT-LOOP TESTS PASSED")


asyncio.run(main())
