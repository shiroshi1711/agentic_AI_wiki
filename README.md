# Elarion AI Wiki (Ella)

Telegram bot + local AI (Ollama / Qwen3) that reads and, with your approval, edits your Obsidian vault.

## Map of the code (read in this order when you reverse-engineer it)

| Step | File | In one sentence |
|---|---|---|
| 1 | `app/main.py` | Starts the bot and plugs in the door guard. |
| 2 | `app/bot/middleware.py` | Only your Telegram user ID gets through (messages AND button taps). |
| 3 | `app/bot/handlers.py` | Every command and the Approve/Reject buttons. Plain messages go to the agent. |
| 4 | `app/agent/loop.py` | The agent loop: model asks for a tool -> we run it -> model sees the result -> repeat (max 5). |
| 5 | `app/agent/tool_registry.py` | The real Python functions Ella can use (search, read, propose edits...). |
| 6 | `app/tools/write.py` | The ONLY code that writes to the vault. Used only after you tap Approve. |
| 7 | `app/tools/preview.py` | Builds the before/after text shown above the Approve button. |
| 8 | `app/storage/database.py` | SQLite tables: search indexes, graph, and pending proposals. |
| 9 | `app/storage/audit.py` | A diary of every change (`/changes` shows the latest). |
| 10 | `app/writing/chapters.py` | Chapter writing: gathers lore + the end of your latest chapter, asks the model for a chapter, splits off the continuity notes. |
| 11 | `app/tools/explain.py` | Covers a LONG note section by section (summarise each part, then Ella explains from the summaries). |
| 12 | `app/retrieval/*`, `app/graph/*` | Finding information: keyword + meaning search, and the character graph. |

## The safety idea
Ella can only PREPARE a change (`propose_*` tools). You see the exact change, then Approve or Reject.
On Approve: the note is checked for "did it change meanwhile?", backed up outside the vault, then replaced.

## Settings (`.env`)
`TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_USER_ID`, `VAULT_PATH`, `LLM_MODEL`, `EMBEDDING_MODEL`,
optional: `OLLAMA_URL` (default `http://127.0.0.1:11434`), `LLM_NUM_CTX` (default `8192`),
`CHAPTERS_FOLDER` (folder inside your vault for approved chapters, default `Story Building/Chapters`), `CHAPTER_MAX_TOKENS` (default `3500`).

## Tests that need no Telegram and no Ollama
`python test_edit_tools.py`, `python test_agent_loop_fake.py`, `python test_approval_flow.py`, `python test_chapter_flow.py`, `python test_retrieval_quality.py`, `python test_explain_note.py`
(each runs in a throwaway vault and never touches your real notes).

## Writing chapters
Tell Ella what you want ("write a chapter where Lumiere returns after the war"). She calls `draft_chapter`,
you get the full draft in Telegram plus Approve / Reject. To change it, just say what to change
("make it darker") and she calls `revise_chapter`; the old draft is replaced. Drafts stay valid for 24 hours.
Approved chapters are saved to `CHAPTERS_FOLDER`. "Latest chapter" is found by name order (Chapter 2 before Chapter 10).

## Explaining events and other non-character notes
Search ignores filler words ("what", "the", "jelaskan"...) and counts a match in a note's TITLE much more than in its body.
Each chunk is embedded together with its note's title/folder (so run `/reindex` after updating!).
Long notes reach the model as: the beginning + the passages that matched the question. To cover a whole long note,
Ella uses `explain_note`. All tool results of one request together are limited (see `app/agent/loop.py`).
