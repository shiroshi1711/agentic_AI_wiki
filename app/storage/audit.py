"""
A simple "diary" of everything Ella changed in your vault.

Each line in the file is one JSON record, so it is easy to read,
easy to search, and nothing in it can break the database.
"""

import json
from datetime import datetime, timezone

from app.storage.database import DB_PATH


AUDIT_LOG_PATH = DB_PATH.parent / "changes.log"


def log_change(
    proposal: dict,
    status: str,
    detail: str = "",
) -> None:
    """Append one record. Logging must never crash the bot."""

    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "proposal_id": proposal.get("proposal_id"),
        "operation": proposal.get("operation"),
        "note_path": proposal.get("note_path"),
        "status": status,
        "detail": detail,
    }

    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_recent_changes(limit: int = 10) -> list[dict]:
    """Return the newest records first."""

    if not AUDIT_LOG_PATH.is_file():
        return []

    records = []

    try:
        lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for line in reversed(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

        if len(records) >= limit:
            break

    return records
