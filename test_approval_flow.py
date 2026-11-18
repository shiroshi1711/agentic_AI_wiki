"""
Tests the Approve / Reject buttons using FAKE Telegram objects (no internet,
no real bot). Also checks that the proposal message cannot be broken by
special characters in a note.

Run:  python test_approval_flow.py
"""
import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

SANDBOX = Path(tempfile.mkdtemp(prefix="ella-test-"))
(SANDBOX / "vault").mkdir(parents=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(SANDBOX / "home")
os.environ["VAULT_PATH"] = str(SANDBOX / "vault")

from app.agent.tool_registry import propose_create_note, propose_edit_note
from app.bot import handlers
from app.storage.audit import read_recent_changes
from app.storage.database import get_pending_change, initialize_database

initialize_database()
VAULT = SANDBOX / "vault"
(VAULT / "Lumiere.md").write_text("Occupation: Knight\n", encoding="utf-8")

CHAT, USER = 5, 7
index_calls = []


async def fake_rebuild():
    index_calls.append(1)


handlers.rebuild_indexes = fake_rebuild


def fake_callback(kind, proposal_id, user_id=USER):
    message = SimpleNamespace(chat=SimpleNamespace(id=CHAT), edit_text=AsyncMock())
    return SimpleNamespace(
        data=f"{kind}:{proposal_id}",
        from_user=SimpleNamespace(id=user_id),
        message=message,
        answer=AsyncMock(),
    )


async def main():
    # --- the proposal message survives Markdown-breaking characters ------
    risky = "# Aria_the_*Physician* [[Northern Kingdom]] `x` _unclosed"
    created = await propose_create_note("Aria.md", risky, chat_id=CHAT, user_id=USER)
    sent = SimpleNamespace(answer=AsyncMock())
    await handlers.send_pending_proposals(sent, CHAT, USER, "2000-01-01T00:00:00")
    kwargs = sent.answer.call_args.kwargs
    assert "parse_mode" not in kwargs and kwargs["reply_markup"] is not None
    assert risky in sent.answer.call_args.args[0]
    print("OK   proposal message has buttons, no Markdown mode, shows risky text intact")

    # --- someone else cannot approve --------------------------------------
    stranger = fake_callback("approve", created["proposal_id"], user_id=999)
    await handlers.approve_proposal(stranger)
    assert "cannot approve" in stranger.answer.call_args.args[0]
    assert not (VAULT / "Aria.md").exists()
    print("OK   another user cannot approve")

    # --- approve: button answered FIRST, then saved, then indexed ---------
    callback = fake_callback("approve", created["proposal_id"])
    await handlers.approve_proposal(callback)
    assert (VAULT / "Aria.md").read_text(encoding="utf-8") == risky
    assert callback.answer.call_count == 1
    assert get_pending_change(created["proposal_id"])["status"] == "completed"
    assert index_calls == [1]
    last_text = callback.message.edit_text.call_args_list[-1].args[0]
    assert "up to date" in last_text
    print("OK   approve: note saved, status completed, indexes refreshed, user told")

    # --- double approve is blocked ----------------------------------------
    again = fake_callback("approve", created["proposal_id"])
    await handlers.approve_proposal(again)
    assert "no longer pending" in again.answer.call_args.args[0]
    assert index_calls == [1]
    print("OK   second tap on Approve does nothing")

    # --- indexing failure does NOT make a saved note look failed ----------
    async def broken_rebuild():
        raise RuntimeError("Ollama is off")

    handlers.rebuild_indexes = broken_rebuild
    edit = await propose_edit_note("Lumiere.md", "Knight", "King", chat_id=CHAT, user_id=USER)
    callback = fake_callback("approve", edit["proposal_id"])
    await handlers.approve_proposal(callback)
    assert (VAULT / "Lumiere.md").read_text(encoding="utf-8") == "Occupation: King\n"
    assert get_pending_change(edit["proposal_id"])["status"] == "completed"
    assert "/reindex" in callback.message.edit_text.call_args_list[-1].args[0]
    print("OK   index failure: note stays saved/completed, user is told to run /reindex")

    # --- reject leaves the vault alone --------------------------------------
    edit2 = await propose_edit_note("Lumiere.md", "King", "Emperor", chat_id=CHAT, user_id=USER)
    callback = fake_callback("reject", edit2["proposal_id"])
    await handlers.reject_proposal(callback)
    assert (VAULT / "Lumiere.md").read_text(encoding="utf-8") == "Occupation: King\n"
    assert get_pending_change(edit2["proposal_id"])["status"] == "rejected"
    print("OK   reject: vault unchanged, status rejected")

    # --- the diary recorded everything --------------------------------------
    statuses = [r["status"] for r in read_recent_changes(10)]
    assert statuses == ["rejected", "completed", "completed"], statuses
    print("OK   change log has all 3 events:", statuses)

    print("\nALL APPROVAL-FLOW TESTS PASSED")


asyncio.run(main())
