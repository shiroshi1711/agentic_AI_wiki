import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.agent.loop import run_agent
from app.config.settings import get_settings
from app.graph.indexer import index_character_graph
from app.llm.ollama_provider import generate_response
from app.retrieval.indexer import index_vault
from app.retrieval.semantic_indexer import index_vault_semantic
from app.storage.audit import log_change, read_recent_changes
from app.storage.database import (
    expire_pending_changes,
    get_pending_change,
    get_pending_changes,
    update_proposal_status,
)
from app.storage.memory import clear_history, get_history, save_message
from app.tools.preview import build_proposal_preview, split_for_telegram
from app.writing.chapters import is_chapter_path
from app.tools.read import read_note
from app.tools.search import search_vault
from app.tools.write import create_note, delete_note, update_note


logger = logging.getLogger(__name__)

router = Router()


@asynccontextmanager
async def keep_typing(message: Message):
    """
    Telegram's "typing..." only lasts ~5 seconds. A chapter can take minutes,
    so re-send it every 4 seconds while the bot works.
    """

    async def repeat():
        while True:
            try:
                await message.bot.send_chat_action(
                    chat_id=message.chat.id,
                    action="typing",
                )
            except Exception:
                pass

            await asyncio.sleep(4)

    task = asyncio.create_task(repeat())

    try:
        yield
    finally:
        task.cancel()


# ---------------------------------------------------------------------------
# Approval flow: Ella PROPOSES, you decide.
# ---------------------------------------------------------------------------

async def send_pending_proposals(
    message: Message,
    chat_id: int,
    user_id: int,
    created_after: str,
):
    proposals = get_pending_changes(
        chat_id,
        user_id,
        created_after,
    )

    for proposal in proposals:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Approve",
                        callback_data=f"approve:{proposal['proposal_id']}",
                    ),
                    InlineKeyboardButton(
                        text="❌ Reject",
                        callback_data=f"reject:{proposal['proposal_id']}",
                    ),
                ]
            ]
        )

        if proposal["operation"] == "delete":
            # Deleting gets its own, unmistakable buttons.
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🗑️ Yes, delete this note",
                            callback_data=f"approve:{proposal['proposal_id']}",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text="↩️ No, keep it",
                            callback_data=f"reject:{proposal['proposal_id']}",
                        ),
                    ],
                ]
            )

            await message.answer(
                "⚠️ Delete note?\n\n"
                f"Path: {proposal['note_path']}\n\n"
                f"{build_proposal_preview(proposal)}\n\n"
                "Nothing has been deleted yet.",
                reply_markup=keyboard,
            )
            continue

        if proposal["operation"] == "create" and is_chapter_path(proposal["note_path"]):
            # A chapter is long: send the WHOLE draft in pieces, then the buttons.
            for piece in split_for_telegram(proposal["content"]):
                await message.answer(piece)

            await message.answer(
                "📖 Chapter draft ready.\n"
                f"It would be saved as: {proposal['note_path']}\n\n"
                "Nothing is saved yet. Approve to save it, reject to discard "
                "it, or just tell me what to change and I will rewrite it.",
                reply_markup=keyboard,
            )
            continue

        # Plain text on purpose (no parse_mode): note text often contains
        # characters like _ * [ ] that Telegram's Markdown refuses.
        await message.answer(
            "📝 Note change proposal\n\n"
            f"Operation: {proposal['operation']}\n"
            f"Path: {proposal['note_path']}\n\n"
            f"{build_proposal_preview(proposal)}\n\n"
            "Nothing has been changed yet. Approve or reject?",
            reply_markup=keyboard,
        )


def get_valid_proposal(
    callback: CallbackQuery,
    proposal_id: str,
) -> tuple[dict | None, str | None]:

    expire_pending_changes()

    proposal = get_pending_change(proposal_id)

    if proposal is None:
        return None, "Proposal not found."

    if callback.message is None:
        return None, "Message is unavailable."

    if proposal["user_id"] != callback.from_user.id:
        return None, "You cannot approve this proposal."

    if proposal["chat_id"] != callback.message.chat.id:
        return None, "This proposal belongs to another chat."

    if proposal["status"] != "pending":
        return None, "This proposal is no longer pending."

    return proposal, None


async def safe_edit(callback: CallbackQuery, text: str) -> None:
    """Edit the proposal message; a failed edit must never break the flow."""
    if callback.message is None:
        return

    try:
        await callback.message.edit_text(text)
    except Exception:
        logger.warning("Could not edit the proposal message.", exc_info=True)


async def rebuild_indexes() -> None:
    """Refresh keyword, semantic, and graph indexes after a change."""
    settings = get_settings()

    # The keyword and graph indexes are normal (blocking) functions.
    # to_thread runs them on the side so the bot stays responsive.
    await asyncio.to_thread(index_vault)
    await index_vault_semantic()
    await asyncio.to_thread(index_character_graph, settings.vault_path)


@router.callback_query(F.data.startswith("approve:"))
async def approve_proposal(callback: CallbackQuery):
    proposal_id = callback.data.split(":", 1)[1]

    proposal, error = get_valid_proposal(callback, proposal_id)

    if error:
        await callback.answer(error, show_alert=True)
        return

    # Claim the proposal so it cannot be approved twice.
    claimed = update_proposal_status(
        proposal_id,
        expected_status="pending",
        new_status="approved",
    )

    if not claimed:
        await callback.answer(
            "This proposal has already been processed.",
            show_alert=True,
        )
        return

    # Answer the button RIGHT AWAY. Telegram expects a quick reply, and
    # everything below (especially re-indexing) can be slow.
    await callback.answer("Working on it...")

    try:
        if proposal["operation"] == "create":
            result = create_note(
                proposal["note_path"],
                proposal["content"],
            )

        elif proposal["operation"] == "update":
            result = update_note(
                proposal["note_path"],
                proposal["content"],
                expected_hash=proposal["original_hash"],
            )

        elif proposal["operation"] == "delete":
            result = delete_note(
                proposal["note_path"],
                expected_hash=proposal["original_hash"],
            )

        else:
            raise ValueError("Unknown proposal operation.")

    except Exception as error:
        update_proposal_status(
            proposal_id,
            expected_status="approved",
            new_status="failed",
        )
        log_change(proposal, "failed", str(error))

        await safe_edit(
            callback,
            f"⚠️ Proposal failed. Your note was not changed.\n\n{error}",
        )
        raise

    # The note is saved. Record it before anything else can go wrong.
    update_proposal_status(
        proposal_id,
        expected_status="approved",
        new_status="completed",
    )
    log_change(proposal, "completed", result)

    await safe_edit(
        callback,
        f"✅ Proposal approved!\n\n{result}\n\n"
        "Updating Ella's search indexes...",
    )

    try:
        await rebuild_indexes()
        await safe_edit(
            callback,
            f"✅ Proposal approved!\n\n{result}\n\n"
            "Search indexes are up to date.",
        )
    except Exception:
        logger.exception("Re-indexing after approval failed.")
        await safe_edit(
            callback,
            f"✅ Proposal approved!\n\n{result}\n\n"
            "⚠️ The note is saved, but updating the search indexes "
            "failed. Run /reindex when Ollama is available.",
        )


@router.callback_query(F.data.startswith("reject:"))
async def reject_proposal(callback: CallbackQuery):
    proposal_id = callback.data.split(":", 1)[1]

    proposal, error = get_valid_proposal(
        callback,
        proposal_id,
    )

    if error:
        await callback.answer(error, show_alert=True)
        return

    rejected = update_proposal_status(
        proposal_id,
        expected_status="pending",
        new_status="rejected",
    )

    if not rejected:
        await callback.answer(
            "This proposal has already been processed.",
            show_alert=True,
        )
        return

    log_change(proposal, "rejected")

    await callback.answer("Proposal rejected.")

    await safe_edit(
        callback,
        f"❌ Proposal rejected.\n\n"
        f"Operation: {proposal['operation']}\n"
        f"Note: {proposal['note_path']}\n\n"
        "Your Obsidian vault was not changed.",
    )


@router.message(Command("changes"))
async def changes_command(message: Message):
    records = read_recent_changes(limit=10)

    if not records:
        await message.answer("No changes have been recorded yet.")
        return

    lines = ["🗒️ Recent changes (newest first):\n"]

    for record in records:
        lines.append(
            f"• {record['time'][:16].replace('T', ' ')} UTC | "
            f"{record['status']} | {record['operation']} | "
            f"{record['note_path']}"
        )

    await message.answer("\n".join(lines))


@router.message(Command("start"))
async def start_command(message: Message):
    await message.answer(
        "Elarion AI Wiki is online.\n\n"
        "Welcome back, Creator."
    )


@router.message(Command("reindex"))
async def reindex_command(message: Message):
    await message.answer(
        "Rebuilding Elarion's knowledge systems...\n"
        "This may take a while."
    )

    try:
        # 1. Rebuild keyword search index
        note_count = index_vault()

        # 2. Rebuild semantic search index
        chunk_count = await index_vault_semantic()

        # 3. Rebuild character knowledge graph
        settings = get_settings()
        graph_stats = index_character_graph(settings.vault_path)

        await message.answer(
            "Knowledge rebuild complete!\n\n"
            f"Keyword index: {note_count} notes\n"
            f"Semantic index: {chunk_count} chunks\n"
            f"Knowledge graph:\n"
            f"- {graph_stats['characters_parsed']} characters\n"
            f"- {graph_stats['entities']} entities\n"
            f"- {graph_stats['attributes']} attributes\n"
            f"- {graph_stats['relationships']} relationships"
        )

    except Exception:
        await message.answer(
            "Knowledge rebuild failed. Check the application logs."
        )
        raise

@router.message(Command("search"))
async def search_command(
    message: Message,
    command: CommandObject,
):
    query = (command.args or "").strip()

    if not query:
        await message.answer(
            "Usage: /search <keyword>\n"
            "Example: /search dragon"
        )
        return

    try:
        results = search_vault(query)

        if not results:
            await message.answer(
                f"No matches found for: {query}"
            )
            return

        response = [f"Results for: {query}\n"]

        for result in results:
            response.append(
                f"{result['title']}\n"
                f"Path: {result['file']}\n"
                f"{result['snippet']}\n"
            )

        await message.answer("\n".join(response))

    except Exception:
        await message.answer("Search failed. Check the application logs.")
        raise


@router.message(Command("read"))
async def read_command(
    message: Message,
    command: CommandObject,
):
    note_path = (command.args or "").strip()

    if not note_path:
        await message.answer(
            "Usage: /read <note_path>\n"
            "Example: /read Characters/Azrael.md"
        )
        return

    try:
        content = read_note(note_path)

        max_length = 3500

        if len(content) > max_length:
            content = (
                content[:max_length]
                + "\n\n...[Note truncated.]"
            )

        await message.answer(f"{note_path}\n\n{content}")

    except (ValueError, FileNotFoundError, OSError, UnicodeError) as error:
        await message.answer(f"⚠️ {error}")


@router.message(Command("ask"))
async def ask_command(
    message: Message,
    command: CommandObject,
):
    prompt = (command.args or "").strip()

    if not prompt:
        await message.answer(
            "Usage: /ask <your question>"
        )
        return

    user = message.from_user

    if user is None:
        return

    chat_id = message.chat.id
    user_id = user.id

    await message.bot.send_chat_action(
        chat_id=chat_id,
        action="typing",
    )

    try:
        history = get_history(chat_id, user_id)

        answer = await generate_response(
            prompt,
            history=history,
        )
        save_message(chat_id, user_id, "user", prompt)
        save_message(chat_id, user_id, "assistant", answer)

        for start in range(0, len(answer), 3500):
            await message.answer(answer[start:start + 3500])

    except Exception:
        await message.answer(
            "⚠️ Something went wrong while generating a response."
        )
        raise


@router.message(Command("lore"))
async def lore_command(
    message: Message,
    command: CommandObject,
):
    question = (command.args or "").strip()

    if not question:
        await message.answer(
            "Usage: /lore <question>"
        )
        return

    user = message.from_user

    if user is None:
        return

    chat_id = message.chat.id
    user_id = user.id

    await message.bot.send_chat_action(
        chat_id=chat_id,
        action="typing",
    )

    try:
        request_started_at = datetime.now(timezone.utc).isoformat()
        history = get_history(chat_id, user_id)

        async with keep_typing(message):
            answer = await run_agent(
                question,
                history=history,
                chat_id=chat_id,
                user_id=user_id,
            )

        save_message(chat_id, user_id, "user", question)
        save_message(chat_id, user_id, "assistant", answer)

        for start in range(0, len(answer), 3500):
            await message.answer(
                answer[start:start + 3500]
            )
        await send_pending_proposals(
            message,
            chat_id,
            user_id,
            request_started_at,
            )

    except Exception:
        await message.answer(
            "⚠️ Something went wrong while Ella was thinking."
        )
        raise

@router.message(Command("forget"))
async def forget_command(message: Message):
    user = message.from_user

    if user is None:
        return

    clear_history(
        chat_id=message.chat.id,
        user_id=user.id,
    )

    await message.answer(
        "🧹 Conversation history cleared.\n"
        "We can start fresh!"
    )


@router.message()
async def chat_handler(message: Message):
    # Ignore non-text messages.
    if not message.text:
        return

    # Don't intercept slash commands.
    if message.text.startswith("/"):
        return

    user = message.from_user

    if user is None:
        return

    chat_id = message.chat.id
    user_id = user.id
    prompt = message.text.strip()

    if not prompt:
        return

    await message.bot.send_chat_action(
        chat_id=chat_id,
        action="typing",
    )

    try:
        request_started_at = datetime.now(timezone.utc).isoformat()
        history = get_history(chat_id, user_id)

        async with keep_typing(message):
            answer = await run_agent(
                prompt,
                history=history,
                chat_id=chat_id,
                user_id=user_id,
            )

        save_message(chat_id, user_id, "user", prompt)
        save_message(chat_id, user_id, "assistant", answer)

        for start in range(0, len(answer), 3500):
            await message.answer(
                answer[start:start + 3500]
            )

        await send_pending_proposals(
            message,
            chat_id,
            user_id,
            request_started_at,
        )
        
    except Exception:
        await message.answer(
            "⚠️  Ella encountered an error. Please try again."
        )
        raise
