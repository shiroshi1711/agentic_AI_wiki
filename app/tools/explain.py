"""
Explaining LONG notes (a major event, a history, a magic system...).

A small model cannot hold a 20,000-character note in its head at once.
So we do it like a student making study notes:
  1. cut the note into sections,
  2. summarise each section on its own (facts only),
  3. give those compact summaries to Ella, who writes the final explanation.
Short notes need none of this and are returned whole.
"""

import re

from app.llm.ollama_provider import generate_response
from app.retrieval.chunker import chunk_text
from app.tools.read import read_note


SHORT_NOTE_CHARS = 5000   # up to this size, the whole note is returned
SECTION_CHARS = 3500      # size of each piece that gets summarised
MAX_SECTIONS = 8          # keeps the result small enough for the model
SUMMARY_TOKENS = 250      # max length of each section summary


SUMMARIZER_PROMPT = """\
You extract facts from one part of a worldbuilding note.
- Use ONLY what is written in the text. Add nothing.
- Keep names, places, dates and special terms exactly as written.
- Write at most 8 short bullet points covering: what happens, who is \
involved, when and where, causes, and consequences.
- If this part contains none of these, write: - (nothing relevant)
"""


def split_into_sections(text: str) -> list[str]:
    """Cut a note at headings when possible, into pieces of about SECTION_CHARS."""
    blocks = re.split(r"\n(?=#{1,3} )", text)

    sections = []
    current = ""

    for block in blocks:
        if len(block) <= SECTION_CHARS:
            pieces = [block]
        else:
            pieces = chunk_text(block, SECTION_CHARS, 150)

        for piece in pieces:
            if current and len(current) + len(piece) + 2 > SECTION_CHARS:
                sections.append(current)
                current = piece
            else:
                current = f"{current}\n\n{piece}" if current else piece

    if current:
        sections.append(current)

    return sections


async def explain_note(note_path: str, focus: str = "") -> dict:
    """
    Prepare a note for explanation.
    Short note -> the full text. Long note -> one fact summary per section.
    """

    text = read_note(note_path)

    if len(text) <= SHORT_NOTE_CHARS:
        return {
            "note_path": note_path,
            "complete": True,
            "text": text,
        }

    sections = split_into_sections(text)
    covered = sections[:MAX_SECTIONS]

    summaries = []

    for number, section in enumerate(covered, start=1):
        prompt = (
            f"Note: {note_path}\n"
            f"This is part {number} of {len(sections)}.\n"
            + (f"Pay special attention to: {focus}\n" if focus.strip() else "")
            + f"\nTEXT:\n{section}"
        )

        summary = await generate_response(
            prompt,
            system_prompt=SUMMARIZER_PROMPT,
            max_tokens=SUMMARY_TOKENS,
        )

        summaries.append({"part": number, "facts": summary})

    result = {
        "note_path": note_path,
        "complete": len(covered) == len(sections),
        "parts_total": len(sections),
        "parts_summarized": len(covered),
        "summaries": summaries,
        "how_to_use": (
            "These are fact summaries of consecutive parts of the note, in "
            "order. Explain the whole note from them in your own words."
        ),
    }

    if len(covered) < len(sections):
        result["warning"] = (
            f"The note is very long: only the first {len(covered)} of "
            f"{len(sections)} parts were summarised."
        )

    return result
