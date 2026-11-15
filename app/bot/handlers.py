from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.filters.command import CommandObject
from app.llm.ollama_provider import generate_response
from app.tools.search import search_vault
from app.tools.read import read_note
from app.retrieval.indexer import index_vault
from app.retrieval.semantic_indexer import index_vault_semantic
from app.graph.indexer import index_character_graph
from app.config.settings import get_settings
from app.retrieval.context import retrieve_context
from app.storage.memory import ( get_history,  save_message, clear_history)
from app.llm.query_rewriter import rewrite_lore_query
from app.graph.context import retrieve_graph_context
from app.agent.loop import run_agent
from datetime import datetime, timezone
from aiogram import F
from aiogram.types import (CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,)
from app.storage.database import (get_pending_changes,get_pending_change, update_proposal_status,expire_pending_changes,)
from app.tools.write import (create_note,update_note,get_note_hash,)


router = Router()

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
                        text=" Approve",
                        callback_data=f"approve:{proposal['proposal_id']}",
                    ),
                    InlineKeyboardButton(
                        text=" Reject",
                        callback_data=f"reject:{proposal['proposal_id']}",
                    ),
                ]
            ]
        )

        await message.answer(
            f" **Note change proposal**\n\n"
            f"Operation: {proposal['operation']}\n"
            f"Path: {proposal['note_path']}\n\n"
            f"Preview:\n{proposal['content'][:1500]}\n\n"
            "Nothing has been changed yet. Approve or reject?",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )


def get_valid_proposal(callback: CallbackQuery,proposal_id: str,) -> tuple[dict | None, str | None]:

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


@router.callback_query(F.data.startswith("approve:"))
async def approve_proposal(callback: CallbackQuery):
    proposal_id = callback.data.split(":", 1)[1]

    proposal, error = get_valid_proposal(callback,proposal_id,)

    if error:
        await callback.answer(error, show_alert=True)
        return

    # Claim the proposal so it cannot be approved twice.
    claimed = update_proposal_status(proposal_id,expected_status="pending",new_status="approved",)

    if not claimed:
        await callback.answer("This proposal has already been processed.",show_alert=True,)
        return

    try:
        if proposal["operation"] == "create":
            result = create_note(proposal["note_path"],proposal["content"],)

        elif proposal["operation"] == "update":
            result = update_note(proposal["note_path"],proposal["content"],
                expected_hash=proposal["original_hash"],)

        else:
            raise ValueError("Unknown proposal operation.")

        update_proposal_status(proposal_id,expected_status="approved",
            new_status="completed",)

        # Refresh Ella's knowledge indexes after the file is written.
        try:
            settings = get_settings()
            index_vault()
            await index_vault_semantic()
            index_character_graph(settings.vault_path)
        except Exception:
        # The note is already saved. Indexing can be retried with /reindex.
            pass

        await callback.answer("Approved! Note updated.")

        if callback.message:
            await callback.message.edit_text(
                f"✅ **Proposal approved!**\n\n{result}",
                parse_mode="Markdown",
            )

    except Exception as error:
        update_proposal_status(
            proposal_id,
            expected_status="approved",
            new_status="failed",
        )

        await callback.answer(
            "The change failed. Your note was not successfully updated.",
            show_alert=True,
        )

        if callback.message:
            await callback.message.edit_text(
                f"⚠️ Proposal failed.\n\n{error}"
            )

        raise

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

    await callback.answer("Proposal rejected.")

    if callback.message:
        await callback.message.edit_text(
            f"❌ Proposal rejected.\n\n"
            f"Operation: {proposal['operation']}\n"
            f"Note: {proposal['note_path']}\n\n"
            "Your Obsidian vault was not changed."
        )



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

        answer = await run_agent(
            question,
            history=history,
            chat_id=chat_id,
            user_id=user_id
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

        answer = await run_agent(
            prompt,
            history=history,
            chat_id=chat_id,
            user_id=user_id
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
