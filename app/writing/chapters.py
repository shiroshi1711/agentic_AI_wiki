"""
Chapter writing: everything Ella needs to draft and revise a story chapter.

The flow (the chapter text itself is NEVER written straight into your vault):
  1. Gather lore (keyword + meaning search, character graph) and the end of
     your latest chapter, so the new chapter continues the story.
  2. Ask the model to write ONE complete chapter (plain text, no tool JSON,
     which is much more reliable for a small model).
  3. Split the model's reply into the chapter and its "continuity notes".
  4. The caller turns the chapter into a PROPOSAL; you approve or reject it.
"""

import re
from pathlib import PurePosixPath

from app.config.settings import get_settings
from app.graph.context import retrieve_graph_context
from app.llm.ollama_provider import generate_response, strip_thinking
from app.retrieval.context import retrieve_context
from app.tools.read import read_note


NOTES_MARKER = "=== CONTINUITY NOTES ==="

# Chapters take a while to read and think about, so their proposals
# stay valid for 24 hours instead of 30 minutes.
CHAPTER_PROPOSAL_MINUTES = 24 * 60

MIN_CHAPTER_CHARS = 200
LORE_CHARS = 6000
STORY_SO_FAR_CHARS = 3000


WRITER_SYSTEM_PROMPT = f"""\
You are Ella, a creative writing partner for the author of the Elarion \
universe. You write chapter drafts; the author decides what is kept.

RULES
- Write in the same language and style as the story so far and the lore.
- The LORE section is established fact. Never contradict it.
- Do NOT invent major new facts (new named characters, deaths, magic rules, \
family ties). Small sensory details and minor background are fine.
- Follow the author's instructions about what happens in the chapter.
- Write finished story prose: scenes, dialogue and action. No outline, no \
summary, no commentary, no title line.
- Unless the author asks for another length, write about 1000 words.

AFTER THE CHAPTER, write this exact line on its own:
{NOTES_MARKER}
Then up to 5 short bullet points: new facts you had to invent, and anything \
in the author's instructions that conflicts with the lore. \
If there is nothing to report, write "- None".
"""


# ---------------------------------------------------------------------------
# Paths and names
# ---------------------------------------------------------------------------

def chapters_folder() -> str:
    """The chapters folder as a clean, vault-relative path (forward slashes)."""
    folder = get_settings().chapters_folder.replace("\\", "/").strip("/")
    return folder or "Chapters"


def is_chapter_path(note_path: str) -> bool:
    """True if a note path lives inside the chapters folder."""
    return PurePosixPath(note_path.replace("\\", "/")).parts[
        : len(PurePosixPath(chapters_folder()).parts)
    ] == PurePosixPath(chapters_folder()).parts


def safe_chapter_title(title: str) -> str:
    """Make a title safe to use as a file name."""
    cleaned = re.sub(r'[\\/:*?"<>|#^\[\]]', " ", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] or "Untitled Chapter"


def unique_chapter_path(title: str) -> str:
    """Pick a path that does not exist yet: 'Title.md', 'Title (2).md', ..."""
    vault = get_settings().vault_path
    base = safe_chapter_title(title)
    candidate = base
    number = 2

    while (vault / chapters_folder() / f"{candidate}.md").exists():
        candidate = f"{base} ({number})"
        number += 1

    return f"{chapters_folder()}/{candidate}.md"


def _natural_key(name: str) -> list:
    """Sort 'Chapter 2' before 'Chapter 10'."""
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", name)
    ]


# ---------------------------------------------------------------------------
# Gathering context
# ---------------------------------------------------------------------------

def get_story_so_far(max_chars: int = STORY_SO_FAR_CHARS) -> str:
    """The list of chapters so far, plus the ending of the latest one."""
    folder = get_settings().vault_path / chapters_folder()

    if not folder.is_dir():
        return ""

    names = sorted(
        (f.name for f in folder.glob("*.md") if f.is_file()),
        key=_natural_key,
    )

    if not names:
        return ""

    parts = ["Chapters so far: " + ", ".join(n[:-3] for n in names[-30:])]

    try:
        latest = read_note(f"{chapters_folder()}/{names[-1]}")
        parts.append(
            f"Ending of the latest chapter ({names[-1][:-3]}):\n"
            + latest[-max_chars:]
        )
    except (OSError, ValueError):
        pass

    return "\n\n".join(parts)


async def gather_writing_context(instructions: str) -> tuple[str, list[str]]:
    """Lore + character facts + story so far, as one block of text."""
    lore, lore_sources = await retrieve_context(
        instructions,
        max_notes=4,
        max_total_chars=LORE_CHARS,
    )
    graph, graph_sources = retrieve_graph_context(instructions)
    story = get_story_so_far()

    sections = []

    if lore:
        sections.append("LORE (established facts):\n" + lore)

    if graph:
        sections.append("CHARACTER FACTS:\n" + graph)

    if story:
        sections.append("STORY SO FAR:\n" + story)

    sources = list(dict.fromkeys(lore_sources + graph_sources))

    return "\n\n".join(sections), sources


# ---------------------------------------------------------------------------
# Reading the model's reply
# ---------------------------------------------------------------------------

def parse_chapter_output(raw: str) -> tuple[str, str]:
    """Split the reply into (chapter text, continuity notes)."""
    text = strip_thinking(raw)

    chapter, _, notes = text.partition(NOTES_MARKER)
    chapter = chapter.strip()

    # If the model added a title line anyway, drop it: we add our own.
    lines = chapter.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        chapter = "\n".join(lines[1:]).strip()

    if len(chapter) < MIN_CHAPTER_CHARS:
        raise ValueError(
            "The model returned too little text for a chapter. "
            "Please try again."
        )

    return chapter, notes.strip()


# ---------------------------------------------------------------------------
# Drafting and revising
# ---------------------------------------------------------------------------

async def _write(prompt: str) -> str:
    settings = get_settings()

    return await generate_response(
        prompt,
        system_prompt=WRITER_SYSTEM_PROMPT,
        max_tokens=settings.chapter_max_tokens,
        timeout_seconds=1800,  # writing a chapter can take a few minutes
    )


async def draft_chapter_text(
    instructions: str,
) -> tuple[str, str, list[str]]:
    """Write a new chapter. Returns (chapter, continuity notes, sources)."""
    context, sources = await gather_writing_context(instructions)

    prompt = (
        f"{context}\n\n" if context else ""
    ) + (
        "AUTHOR'S INSTRUCTIONS FOR THIS CHAPTER:\n"
        f"{instructions}\n\n"
        "Write the chapter now."
    )

    chapter, notes = parse_chapter_output(await _write(prompt))

    return chapter, notes, sources


async def revise_chapter_text(
    draft: str,
    feedback: str,
) -> tuple[str, str, list[str]]:
    """Rewrite a draft using the author's feedback."""
    context, sources = await gather_writing_context(feedback)

    prompt = (
        f"{context}\n\n" if context else ""
    ) + (
        "CURRENT DRAFT:\n"
        f"{draft}\n\n"
        "AUTHOR'S FEEDBACK:\n"
        f"{feedback}\n\n"
        "Rewrite the whole chapter applying the feedback. Keep everything "
        "the feedback does not mention."
    )

    chapter, notes = parse_chapter_output(await _write(prompt))

    return chapter, notes, sources
