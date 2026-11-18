from app.tools.search import search_vault
from app.tools.read import read_note
from app.tools.explain import explain_note as explain_note_impl
from app.retrieval.context import retrieve_context
from app.graph.query import get_character_profile, get_connected_characters
from app.storage.database import (
    create_pending_change,
    get_pending_changes,
    update_proposal_status,
)
from app.storage.audit import log_change
from app.writing.chapters import (
    CHAPTER_PROPOSAL_MINUTES,
    draft_chapter_text,
    is_chapter_path,
    revise_chapter_text,
    safe_chapter_title,
    unique_chapter_path,
)
from app.tools.write import (
    get_note_hash,
    read_note_with_hash,
    apply_text_edit,
    apply_append,
    _validate_note_path,
    _validate_content,
)


async def search_notes(query: str) -> list[dict]:
    """Search Obsidian notes using keyword search."""
    return search_vault(query)


# Longer than this and the model would only see the top of the note.
READ_NOTE_LIMIT = 7000


async def read_note_tool(note_path: str) -> str:
    """Read a Markdown note from the Obsidian vault."""
    text = read_note(note_path)

    if len(text) <= READ_NOTE_LIMIT:
        return text

    return (
        text[:READ_NOTE_LIMIT]
        + f"\n\n...[NOT COMPLETE: this note has {len(text)} characters and "
        "only the first part is shown. Use explain_note to cover all of it.]"
    )


async def explain_note(note_path: str, focus: str = "") -> dict:
    """Prepare a (possibly long) note for explanation, section by section."""
    return await explain_note_impl(note_path, focus)


async def search_lore(query: str) -> dict:
    """Search lore using hybrid keyword and semantic retrieval."""
    # 7500 characters keeps the result inside what the model can use.
    context, sources = await retrieve_context(query, max_total_chars=7500)

    return {
        "context": context,
        "sources": sources,
    }


async def get_character_info(name: str) -> dict | None:
    """Retrieve a character's attributes and relationships."""
    return get_character_profile(name)


async def explore_relationships(
    name: str,
    max_depth: int = 2,
) -> dict:
    """Explore a character's relationship network."""

    connections = get_connected_characters(
        name,
        max_depth=max_depth,
    )

    return {
        "character": name,
        "max_depth": max_depth,
        "connections": connections,
    }


async def propose_create_note(
    note_path: str,
    content: str,
    chat_id: int,
    user_id: int,
) -> dict:
    """Prepare a new note for approval without writing it."""

    _validate_content(content)

    vault_path, target_path = _validate_note_path(note_path)

    if target_path.exists():
        raise FileExistsError(
            f"A note already exists at: {note_path}"
        )

    proposal_id = create_pending_change(
        chat_id=chat_id,
        user_id=user_id,
        operation="create",
        note_path=note_path,
        content=content,
    )

    return {
        "approval_required": True,
        "proposal_id": proposal_id,
        "operation": "create",
        "note_path": note_path,
        "preview": content[:1500],
        "message": "Note creation prepared. Waiting for approval.",
    }


async def propose_update_note(
    note_path: str,
    content: str,
    chat_id: int,
    user_id: int,
) -> dict:
    """Prepare an existing note edit for approval."""

    original_hash = get_note_hash(note_path)

    proposal_id = create_pending_change(
        chat_id=chat_id,
        user_id=user_id,
        operation="update",
        note_path=note_path,
        content=content,
        original_hash=original_hash,
    )

    return {
        "approval_required": True,
        "proposal_id": proposal_id,
        "operation": "update",
        "note_path": note_path,
        "preview": content[:1500],
        "message": "Note edit prepared. Waiting for approval.",
    }


async def propose_edit_note(
    note_path: str,
    old_text: str,
    new_text: str,
    chat_id: int,
    user_id: int,
) -> dict:
    """
    Prepare a small edit: replace ONE exact piece of text in a note.
    Nothing is written until the user approves.
    """

    current, original_hash = read_note_with_hash(note_path)

    new_content = apply_text_edit(current, old_text, new_text)
    _validate_content(new_content)

    proposal_id = create_pending_change(
        chat_id=chat_id,
        user_id=user_id,
        operation="update",
        note_path=note_path,
        content=new_content,
        original_hash=original_hash,
    )

    return {
        "approval_required": True,
        "proposal_id": proposal_id,
        "operation": "edit",
        "note_path": note_path,
        "message": (
            "Edit prepared. The user will now see Approve and Reject "
            "buttons with the exact change. Nothing is saved yet."
        ),
    }


async def propose_append_note(
    note_path: str,
    text: str,
    chat_id: int,
    user_id: int,
) -> dict:
    """
    Prepare adding text to the END of a note.
    Nothing is written until the user approves.
    """

    current, original_hash = read_note_with_hash(note_path)

    new_content = apply_append(current, text)
    _validate_content(new_content)

    proposal_id = create_pending_change(
        chat_id=chat_id,
        user_id=user_id,
        operation="update",
        note_path=note_path,
        content=new_content,
        original_hash=original_hash,
    )

    return {
        "approval_required": True,
        "proposal_id": proposal_id,
        "operation": "append",
        "note_path": note_path,
        "message": (
            "Addition prepared. The user will now see Approve and Reject "
            "buttons with the exact change. Nothing is saved yet."
        ),
    }


def _chapter_result(
    proposal_id: str,
    note_path: str,
    chapter: str,
    notes: str,
    sources: list[str],
    verb: str,
) -> dict:
    """What the model is told after a chapter proposal was created.
    (The chapter itself is deliberately NOT included: it would use up the
    model's memory, and the user receives the full text in Telegram.)"""
    return {
        "approval_required": True,
        "proposal_id": proposal_id,
        "note_path": note_path,
        "word_count": len(chapter.split()),
        "continuity_notes": notes or "None reported.",
        "sources_used": sources,
        "message": (
            f"Chapter draft {verb}. The user will receive the full draft in "
            "Telegram with Approve and Reject buttons. Nothing is saved yet. "
            "Tell the user it is ready, mention the continuity notes briefly, "
            "and say they can ask for changes just by describing them."
        ),
    }


async def draft_chapter(
    title: str,
    instructions: str,
    chat_id: int,
    user_id: int,
) -> dict:
    """Write a NEW chapter draft and prepare it for approval."""

    if not instructions or not instructions.strip():
        raise ValueError("The author's chapter instructions are required.")

    chapter, notes, sources = await draft_chapter_text(instructions)

    note_path = unique_chapter_path(title)
    _validate_note_path(note_path)

    content = f"# {safe_chapter_title(title)}\n\n{chapter}\n"
    _validate_content(content)

    proposal_id = create_pending_change(
        chat_id=chat_id,
        user_id=user_id,
        operation="create",
        note_path=note_path,
        content=content,
        expires_minutes=CHAPTER_PROPOSAL_MINUTES,
    )

    return _chapter_result(
        proposal_id, note_path, chapter, notes, sources, "prepared"
    )


async def revise_chapter(
    feedback: str,
    chat_id: int,
    user_id: int,
) -> dict:
    """Rewrite the chapter draft that is waiting for approval."""

    if not feedback or not feedback.strip():
        raise ValueError("The author's feedback is required.")

    waiting = [
        proposal
        for proposal in get_pending_changes(
            chat_id, user_id, "2000-01-01T00:00:00"
        )
        if proposal["operation"] == "create"
        and is_chapter_path(proposal["note_path"])
    ]

    if not waiting:
        raise ValueError(
            "No chapter draft is waiting for review. "
            "Use draft_chapter to start a new chapter."
        )

    old = waiting[-1]  # the newest draft

    # The saved text starts with "# Title"; the title stays the same.
    first_line, _, body = old["content"].partition("\n")
    title = first_line.lstrip("# ").strip()

    chapter, notes, sources = await revise_chapter_text(
        body.strip(),
        feedback,
    )

    content = f"# {title}\n\n{chapter}\n"
    _validate_content(content)

    proposal_id = create_pending_change(
        chat_id=chat_id,
        user_id=user_id,
        operation="create",
        note_path=old["note_path"],
        content=content,
        expires_minutes=CHAPTER_PROPOSAL_MINUTES,
    )

    # The old draft is replaced: its buttons stop working.
    if update_proposal_status(old["proposal_id"], "pending", "rejected"):
        log_change(old, "rejected", "replaced by a revised draft")

    return _chapter_result(
        proposal_id, old["note_path"], chapter, notes, sources, "revised"
    )

TOOLS = {
    "search_notes": {
        "description": "Search for relevant Markdown notes in the Obsidian vault.",
        "function": search_notes,
    },
    "read_note": {
        "description": "Read the full contents of a specific Markdown note.",
        "function": read_note_tool,
    },
    "search_lore": {
        "description": "Find relevant lore using keyword and semantic search.",
        "function": search_lore,
    },
    "get_character_info": {
        "description": "Retrieve a character's known attributes and relationships.",
        "function": get_character_info,
    },
    "propose_create_note": {
        "description": "Prepare a new Obsidian note for user approval. Does not write directly.",
        "function": propose_create_note,
    },
    "propose_update_note": {
        "description": "Prepare an edit to an existing Obsidian note for user approval. Does not write directly.",
        "function": propose_update_note,
    },
    "propose_edit_note": {
        "description": "Prepare replacing one exact piece of text in a note, for user approval.",
        "function": propose_edit_note,
    },
    "propose_append_note": {
        "description": "Prepare adding text to the end of a note, for user approval.",
        "function": propose_append_note,
    },
    "explain_note": {
        "description": "Cover a whole note, even a long one, section by section.",
        "function": explain_note,
    },
    "draft_chapter": {
        "description": "Write a new story chapter draft for user approval.",
        "function": draft_chapter,
    },
    "revise_chapter": {
        "description": "Rewrite the pending chapter draft using the author's feedback.",
        "function": revise_chapter,
    },
    "explore_relationships": {
        "function": explore_relationships,
        "description": "Explore a character's relationship network and discover connected characters up to a specified depth.",},
}


def get_tool(name: str) -> dict | None:
    """Get a registered tool by its name."""
    return TOOLS.get(name)


def get_available_tools() -> list[dict]:
    """Return tool names and descriptions for the agent."""
    return [
        {
            "name": name,
            "description": tool["description"],
        }
        for name, tool in TOOLS.items()
    ]
