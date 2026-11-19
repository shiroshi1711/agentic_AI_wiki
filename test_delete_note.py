"""
Tests deleting notes safely (and removing just a part of a note).
Runs in a throwaway vault/home with fake Telegram objects and a fake model.

Run:  python test_delete_note.py
"""
import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import web

SANDBOX = Path(tempfile.mkdtemp(prefix="ella-test-"))
VAULT = SANDBOX / "vault"
(VAULT / "Characters").mkdir(parents=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(SANDBOX / "home")
os.environ["VAULT_PATH"] = str(VAULT)
PORT = 18438
os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{PORT}"

from app.storage.database import DB_PATH

# --- Build an OLD-STYLE database (before deletion existed) with one proposal in it.
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
old = sqlite3.connect(DB_PATH)
old.execute("""
    CREATE TABLE pending_changes (
        proposal_id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        operation TEXT NOT NULL CHECK (operation IN ('create', 'update')),
        note_path TEXT NOT NULL, content TEXT NOT NULL, original_hash TEXT,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending','approved','rejected','completed','failed','expired')),
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL)
""")
old.execute("CREATE INDEX idx_pending_changes_status ON pending_changes(status)")
old.execute("INSERT INTO pending_changes VALUES ('old-1', 1, 2, 'create', 'Old.md', 'old text', NULL, 'completed', '2026-11-01T00:00:00', '2026-11-01T00:30:00')")
old.commit()
old.close()

from app.agent import tool_registry
from app.agent.loop import run_agent
from app.bot import handlers
from app.storage.audit import read_recent_changes
from app.storage.database import get_connection, get_pending_change, get_pending_changes, initialize_database
from app.tools.preview import build_proposal_preview
from app.tools.write import delete_note, get_note_hash

CHAT, USER = 8, 9
index_calls = []


async def fake_rebuild():
    index_calls.append(1)


handlers.rebuild_indexes = fake_rebuild

requests_seen, SCRIPT = [], []


async def fake_chat(request):
    requests_seen.append(await request.json())
    return web.json_response(SCRIPT.pop(0))


def tool_call(name, arguments):
    return {"message": {"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}}


def reply(text):
    return {"message": {"role": "assistant", "content": text}}


def note(name, text):
    (VAULT / name).write_text(text, encoding="utf-8")
    return name


def fake_callback(kind, proposal_id, user_id=USER):
    return SimpleNamespace(
        data=f"{kind}:{proposal_id}",
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(chat=SimpleNamespace(id=CHAT), edit_text=AsyncMock()),
        answer=AsyncMock(),
    )


def check(label):
    print("OK  ", label)


async def main():
    app = web.Application()
    app.router.add_post("/api/chat", fake_chat)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()

    # ---- 1. upgrading an OLD database keeps data and allows 'delete' ------
    initialize_database()
    initialize_database()  # running twice must be harmless
    with get_connection() as c:
        kept = c.execute("SELECT note_path, status FROM pending_changes WHERE proposal_id='old-1'").fetchone()
        assert (kept["note_path"], kept["status"]) == ("Old.md", "completed")
        index = c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pending_changes_status'").fetchone()
        assert index is not None
        assert c.execute("SELECT name FROM sqlite_master WHERE name='pending_changes_old'").fetchone() is None
    check("old database upgraded: existing proposal kept, index present, no leftovers, safe to run twice")

    # ---- 2. delete_note: backup first, then delete -------------------------
    victim = note("Characters/Victim.md", "Name: Victim\nA doomed character.\n")
    digest = get_note_hash(victim)
    message = delete_note(victim, expected_hash=digest)
    assert not (VAULT / victim).exists()
    backup = Path(message.split("Backup saved at: ")[1].strip())
    assert backup.read_text(encoding="utf-8") == "Name: Victim\nA doomed character.\n"
    assert not backup.is_relative_to(VAULT)
    check("delete_note: note gone, identical backup exists OUTSIDE the vault")

    # ---- 3. refusals --------------------------------------------------------
    keep = note("Characters/Keep.md", "keep me")
    for label, call, error_type in [
        ("changed since proposal", lambda: delete_note(keep, expected_hash="0" * 64), ValueError),
        ("missing note", lambda: delete_note("Characters/Nobody.md", expected_hash="x"), FileNotFoundError),
        ("path outside vault", lambda: delete_note("../x.md", expected_hash="x"), ValueError),
        ("not a markdown file", lambda: delete_note("a.txt", expected_hash="x"), ValueError),
        ("hidden folder", lambda: delete_note(".obsidian/app.md", expected_hash="x"), ValueError),
    ]:
        try:
            call()
        except error_type:
            pass
        else:
            raise AssertionError(label)
    assert (VAULT / keep).exists()
    check("refused: changed note, missing note, outside path, non-markdown, hidden folder (note untouched)")

    # ---- 4. proposing never deletes; preview is clear -----------------------
    target = note("Characters/Target.md", "Name: Target\n" + "line\n" * 300)
    proposed = await tool_registry.propose_delete_note(target, chat_id=CHAT, user_id=USER)
    assert proposed["approval_required"] and (VAULT / target).exists()
    proposal = get_pending_change(proposed["proposal_id"])
    assert proposal["operation"] == "delete"
    preview = build_proposal_preview(proposal)
    assert "DELETED" in preview and "Name: Target" in preview and "backup" in preview
    check("propose_delete_note: note still exists; preview says DELETED and shows the start of the note")

    # ---- 5. Telegram: distinct buttons -------------------------------------
    sent = SimpleNamespace(answer=AsyncMock())
    await handlers.send_pending_proposals(sent, CHAT, USER, "2000-01-01T00:00:00")
    call = sent.answer.call_args
    buttons = [b.text for row in call.kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["🗑️ Yes, delete this note", "↩️ No, keep it"], buttons
    assert call.args[0].startswith("⚠️ Delete note?")
    check("delete confirmation has its own warning text and unmistakable buttons")

    # ---- 6. stranger cannot confirm; owner can ----------------------------------
    stranger = fake_callback("approve", proposed["proposal_id"], user_id=1234)
    await handlers.approve_proposal(stranger)
    assert (VAULT / target).exists()

    owner = fake_callback("approve", proposed["proposal_id"])
    await handlers.approve_proposal(owner)
    assert not (VAULT / target).exists()
    assert get_pending_change(proposed["proposal_id"])["status"] == "completed"
    assert index_calls == [1]
    entry = read_recent_changes(1)[0]
    assert (entry["operation"], entry["status"]) == ("delete", "completed") and "Backup saved at" in entry["detail"]
    check("only the owner can confirm; note deleted; indexes refreshed; backup path written to the change log")

    # ---- 7. 'No, keep it' keeps it; edited-after-proposal is refused -------
    keeper = note("Characters/Keeper.md", "keeper")
    p1 = await tool_registry.propose_delete_note(keeper, chat_id=CHAT, user_id=USER)
    await handlers.reject_proposal(fake_callback("reject", p1["proposal_id"]))
    assert (VAULT / keeper).exists()
    assert get_pending_change(p1["proposal_id"])["status"] == "rejected"

    p2 = await tool_registry.propose_delete_note(keeper, chat_id=CHAT, user_id=USER)
    (VAULT / keeper).write_text("keeper, edited in Obsidian meanwhile", encoding="utf-8")
    cb = fake_callback("approve", p2["proposal_id"])
    try:
        await handlers.approve_proposal(cb)
    except ValueError:
        pass
    assert (VAULT / keeper).exists()
    assert get_pending_change(p2["proposal_id"])["status"] == "failed"
    assert "changed since" in cb.message.edit_text.call_args_list[-1].args[0]
    check("'No, keep it' keeps the note; a note edited after the proposal is NOT deleted")

    # ---- 8. removing just PART of a note already works ----------------------
    part = note("Characters/Part.md", "Name: Part\nSecret: he is a spy\nHome: North\n")
    result = await tool_registry.propose_edit_note(part, "Secret: he is a spy\n", "", chat_id=CHAT, user_id=USER)
    preview = build_proposal_preview(get_pending_change(result["proposal_id"]))
    diff_lines = preview.split("\n\n", 1)[1].splitlines()
    assert "-Secret: he is a spy" in diff_lines
    assert not [l for l in diff_lines if l.startswith("+")], "nothing should be added"
    assert (VAULT / part).read_text().count("Secret") == 1
    check("removing a sentence = propose_edit_note with empty new_text (shows only a '-' line)")

    # ---- 9. through the agent: the model cannot fake who is asking ---------------
    victim2 = note("Characters/Victim2.md", "bye")
    started = "2000-01-01T00:00:00"
    before = len(get_pending_changes(CHAT, USER, started))
    SCRIPT[:] = [
        tool_call("propose_delete_note", {"note_path": victim2, "chat_id": 555, "user_id": 555}),
        reply("I prepared the deletion. Please confirm."),
    ]
    answer = await run_agent("delete the Victim2 note", chat_id=CHAT, user_id=USER)
    assert answer.startswith("I prepared") and (VAULT / victim2).exists()
    assert len(get_pending_changes(CHAT, USER, started)) == before + 1
    assert not get_pending_changes(555, 555, started)
    check("agent: deletion becomes a proposal for the REAL Telegram user; note untouched")

    await runner.cleanup()
    print("\nALL DELETE-NOTE TESTS PASSED")


asyncio.run(main())
