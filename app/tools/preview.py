"""
Builds the text you see in Telegram before you tap Approve or Reject.

For a NEW note: the start of the note.
For an EDIT: a before/after "diff" of only the lines that change
(lines starting with "-" are removed, lines starting with "+" are added).
"""

import difflib

from app.tools.write import read_note_with_hash


MAX_CREATE_PREVIEW = 1500
MAX_DIFF_PREVIEW = 3000


def build_proposal_preview(proposal: dict) -> str:
    content = proposal["content"]

    if proposal["operation"] == "create":
        text = content[:MAX_CREATE_PREVIEW]

        if len(content) > MAX_CREATE_PREVIEW:
            text += (
                f"\n\n...[{len(content) - MAX_CREATE_PREVIEW} "
                "more characters not shown]"
            )

        return "New note content:\n\n" + text

    # Edit: compare the note as it is NOW with the proposed version.
    try:
        current, _ = read_note_with_hash(proposal["note_path"])
    except (OSError, ValueError) as error:
        return f"(Could not read the current note to compare: {error})"

    diff_lines = list(difflib.unified_diff(
        current.splitlines(),
        content.splitlines(),
        lineterm="",
        n=2,
    ))

    # The first two lines are file-name headers we don't need.
    diff_lines = diff_lines[2:]

    if not diff_lines:
        return "No visible difference from the current note."

    diff_text = "\n".join(diff_lines)

    if len(diff_text) > MAX_DIFF_PREVIEW:
        diff_text = (
            diff_text[:MAX_DIFF_PREVIEW]
            + "\n\n...[diff shortened]"
        )

    return "Changes (- removed, + added):\n\n" + diff_text


def split_for_telegram(text: str, limit: int = 3800) -> list[str]:
    """
    Cut long text into pieces Telegram accepts (max 4096 characters),
    preferring to cut at paragraph or line breaks, never mid-word if avoidable.
    """
    pieces = []
    remaining = text.strip()

    while len(remaining) > limit:
        cut = remaining.rfind("\n\n", 0, limit)

        if cut < limit // 2:
            cut = remaining.rfind("\n", 0, limit)

        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)

        if cut < limit // 2:
            cut = limit

        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        pieces.append(remaining)

    return pieces
