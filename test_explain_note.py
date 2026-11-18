"""
Tests how Ella covers LONG notes: explain_note, the read_note guard,
and the limit on how much tool text one request may pile up.
Uses a fake model (no Ollama needed).

Run:  python test_explain_note.py
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

from aiohttp import web

SANDBOX = Path(tempfile.mkdtemp(prefix="ella-test-"))
VAULT = SANDBOX / "vault"
(VAULT / "Events").mkdir(parents=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(SANDBOX / "home")
os.environ["VAULT_PATH"] = str(VAULT)
PORT = 18437
os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{PORT}"

from app.agent import loop, tool_registry
from app.agent.loop import MIN_TOOL_RESULT_CHARS, TOTAL_TOOL_BUDGET_CHARS, run_agent
from app.storage.database import initialize_database
from app.tools.explain import (
    MAX_SECTIONS, SECTION_CHARS, SHORT_NOTE_CHARS, SUMMARIZER_PROMPT,
    explain_note, split_into_sections,
)

initialize_database()
requests_seen, SCRIPT = [], []


async def fake_chat(request):
    body = await request.json()
    requests_seen.append(body)
    if "tools" in body and SCRIPT:               # agent calls offer tools: scripted replies
        return web.json_response(SCRIPT.pop(0))
    part = body["messages"][-1]["content"].split("part ")[1].split(" ")[0]
    return web.json_response({"message": {"role": "assistant", "content": f"- facts of part {part}"}})


def reply(text):
    return {"message": {"role": "assistant", "content": text}}


def tool_call(name, arguments):
    return {"message": {"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}}


def check(label):
    print("OK  ", label)


def write_note(name, text):
    (VAULT / name).write_text(text, encoding="utf-8")
    return name


async def main():
    app = web.Application()
    app.router.add_post("/api/chat", fake_chat)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()

    # ---- 1. splitting prefers headings and respects the size limit -------
    headed = "\n\n".join(f"## Day {i}\n" + f"Something happened on day {i}. " * 60 for i in range(1, 9))
    sections = split_into_sections(headed)
    assert all(len(s) <= SECTION_CHARS + 50 for s in sections) and len(sections) > 1
    assert all(s.lstrip().startswith("## Day") for s in sections), "sections should start at headings"
    check(f"split at headings: {len(sections)} sections, each within the size limit")

    # ---- 2. short note: whole text, no model call -------------------------
    short = write_note("Events/Small.md", "A small event happened. " * 20)
    result = await explain_note(short)
    assert result["complete"] and result["text"].startswith("A small event") and not requests_seen
    check("short note returned whole, without calling the model")

    # ---- 3. long note: one summary per section, focus passed along --------
    long_name = write_note("Events/The Sundering.md", headed)
    assert len(headed) > SHORT_NOTE_CHARS
    result = await explain_note(long_name, focus="why the council fled")
    assert result["complete"] and result["parts_summarized"] == result["parts_total"] == len(requests_seen)
    assert result["summaries"][0]["facts"] == "- facts of part 1"
    first = requests_seen[0]
    assert first["messages"][0]["content"] == SUMMARIZER_PROMPT
    assert "why the council fled" in first["messages"][-1]["content"]
    assert first["options"]["num_predict"] == 250 and "tools" not in first
    check(f"long note: {len(requests_seen)} sections summarised separately; focus passed; token cap set")

    # ---- 4. huge note: capped, and says so --------------------------------
    requests_seen.clear()
    huge = write_note("Events/Huge.md", "\n\n".join(f"## Part {i}\n" + "Long history. " * 250 for i in range(30)))
    result = await explain_note(huge)
    assert not result["complete"] and result["parts_summarized"] == MAX_SECTIONS == len(requests_seen)
    assert "very long" in result["warning"]
    check(f"huge note: only {MAX_SECTIONS} sections summarised and the result says so")

    # ---- 5. read_note never silently shows only the top of a long note ----
    text = await tool_registry.read_note_tool(long_name)
    assert "NOT COMPLETE" in text and "explain_note" in text
    assert await tool_registry.read_note_tool(short) == (VAULT / short).read_text()
    check("read_note: long note is flagged as incomplete; short note unchanged")

    # ---- 6. a request cannot pile up unlimited tool text -------------------
    requests_seen.clear()
    big = [write_note(f"Events/Big{i}.md", f"Big note {i}. " + "x" * 6800) for i in range(4)]
    SCRIPT[:] = [tool_call("read_note", {"note_path": n}) for n in big] + [reply("done")]
    await run_agent("read them all", chat_id=1, user_id=1)
    tool_texts = [m["content"] for m in requests_seen[-1]["messages"] if m["role"] == "tool"]
    assert len(tool_texts) == 4
    assert sum(len(t) for t in tool_texts) <= TOTAL_TOOL_BUDGET_CHARS + MIN_TOOL_RESULT_CHARS + 4 * 60, [len(t) for t in tool_texts]
    assert "shortened" in tool_texts[-1]
    check(f"4 big tool results stay near the {TOTAL_TOOL_BUDGET_CHARS}-character budget: {[len(t) for t in tool_texts]}")

    # ---- 7. the agent can use explain_note end to end -----------------------
    requests_seen.clear()
    SCRIPT[:] = [
        tool_call("explain_note", {"note_path": long_name, "focus": "causes"}),
        reply("The Sundering was ..."),
    ]
    answer = await run_agent("explain the Sundering", chat_id=1, user_id=1)
    tool_message = [m for m in requests_seen[-1]["messages"] if m["role"] == "tool"][-1]
    payload = json.loads(tool_message["content"])
    assert payload["parts_total"] == len(sections) and "facts of part 1" in tool_message["content"]
    assert answer == "The Sundering was ..."
    check("agent -> explain_note -> summaries -> final answer works end to end")

    await runner.cleanup()
    print("\nALL EXPLAIN-NOTE TESTS PASSED")


asyncio.run(main())
