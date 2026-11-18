"""
Safety tests for the edit tools. Runs in a THROWAWAY vault and a throwaway
home folder, so it can never touch your real notes or database.

Run:  python test_edit_tools.py
"""
import asyncio
import os
import tempfile
from pathlib import Path

# --- sandbox (must happen BEFORE importing anything from app) -------------
SANDBOX = Path(tempfile.mkdtemp(prefix="ella-test-"))
(SANDBOX / "vault" / "Characters").mkdir(parents=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(SANDBOX / "home")
os.environ["VAULT_PATH"] = str(SANDBOX / "vault")

from app.agent.tool_registry import propose_append_note, propose_edit_note
from app.storage.database import get_pending_change, initialize_database
from app.tools.preview import build_proposal_preview
from app.tools.write import apply_append, apply_text_edit, update_note

NOTE = "Characters/Lumiere.md"
NOTE_FILE = SANDBOX / "vault" / NOTE
ORIGINAL = "Name: Lumiere\nOccupation: Knight\nHome: North\n"
NOTE_FILE.write_text(ORIGINAL, encoding="utf-8")
initialize_database()


def expect_error(label, function, *args):
    try:
        function(*args)
    except ValueError as error:
        print(f"OK   {label}: refused -> {error}")
    else:
        raise AssertionError(f"{label}: should have been refused")


# 1. Pure text helpers
assert apply_text_edit(ORIGINAL, "Knight", "King") == ORIGINAL.replace("Knight", "King")
expect_error("text not found", apply_text_edit, ORIGINAL, "Wizard", "King")
expect_error("empty old_text", apply_text_edit, ORIGINAL, "", "King")
expect_error("ambiguous (twice)", apply_text_edit, "Knight and Knight", "Knight", "King")
expect_error("no-op edit", apply_text_edit, ORIGINAL, "Knight", "Knight")
assert apply_append("abc", "xyz") == "abc\nxyz\n"
assert apply_append("abc\n", "xyz\n\n") == "abc\nxyz\n"
expect_error("empty append", apply_append, "abc", "   ")
print("OK   text helpers behave")


# 2. Proposals never write to the vault
result = asyncio.run(propose_edit_note(NOTE, "Knight", "King", chat_id=1, user_id=2))
assert result["approval_required"] is True
assert NOTE_FILE.read_text(encoding="utf-8") == ORIGINAL
print("OK   edit proposal did NOT change the note")

proposal = get_pending_change(result["proposal_id"])
preview = build_proposal_preview(proposal)
assert "-Occupation: Knight" in preview and "+Occupation: King" in preview
print("OK   preview shows a before/after diff:\n" + preview)

result2 = asyncio.run(propose_append_note(NOTE, "Rank: General", chat_id=1, user_id=2))
assert NOTE_FILE.read_text(encoding="utf-8") == ORIGINAL
append_preview = build_proposal_preview(get_pending_change(result2["proposal_id"]))
assert "+Rank: General" in append_preview
print("OK   append proposal did NOT change the note either")

# 3. Approving applies exactly the diff, with a backup
proposal = get_pending_change(result["proposal_id"])
message = update_note(NOTE, proposal["content"], expected_hash=proposal["original_hash"])
assert NOTE_FILE.read_text(encoding="utf-8") == ORIGINAL.replace("Knight", "King")
assert "Backup saved at" in message
print("OK   approved edit applied; backup created")

# 4. The other proposal is now stale (the note changed) and must be refused
proposal2 = get_pending_change(result2["proposal_id"])
expect_error("stale proposal", update_note, NOTE, proposal2["content"], proposal2["original_hash"])

# 5. Bad paths / missing notes
for bad in ["../outside.md", "/etc/passwd.md", ".hidden/x.md", "note.txt"]:
    try:
        asyncio.run(propose_append_note(bad, "x", chat_id=1, user_id=2))
    except ValueError:
        print(f"OK   path refused: {bad}")
    else:
        raise AssertionError(f"path accepted: {bad}")

try:
    asyncio.run(propose_edit_note("Characters/Nobody.md", "a", "b", chat_id=1, user_id=2))
except FileNotFoundError:
    print("OK   missing note refused")

# 6. Line endings (Windows-style notes) survive the round trip
crlf = SANDBOX / "vault" / "Crlf.md"
crlf.write_bytes(b"A: 1\r\nB: 2\r\n")
r = asyncio.run(propose_edit_note("Crlf.md", "B: 2", "B: 3", chat_id=1, user_id=2))
p = get_pending_change(r["proposal_id"])
update_note("Crlf.md", p["content"], expected_hash=p["original_hash"])
assert crlf.read_bytes() == b"A: 1\r\nB: 3\r\n", crlf.read_bytes()
print("OK   Windows line endings preserved")

print("\nALL EDIT-TOOL TESTS PASSED")
