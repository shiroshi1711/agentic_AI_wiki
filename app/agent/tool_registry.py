from app.tools.search import search_vault
from app.tools.read import read_note
from app.retrieval.context import retrieve_context
from app.graph.query import get_character_profile, get_connected_characters
from app.storage.database import create_pending_change
from app.tools.write import get_note_hash, _validate_note_path


async def search_notes(query: str) -> list[dict]:
    """Search Obsidian notes using keyword search."""
    return search_vault(query)


async def read_note_tool(note_path: str) -> str:
    """Read a Markdown note from the Obsidian vault."""
    return read_note(note_path)


async def search_lore(query: str) -> dict:
    """Search lore using hybrid keyword and semantic retrieval."""
    context, sources = await retrieve_context(query)

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
