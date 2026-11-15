from pathlib import Path
from pprint import pprint

from app.graph.parser import parse_character_note


note_path = Path(
    "/home/novia/my_obsidian_vault/"
    "Story Building/Characters/Lance Irvine.md"
)

text = note_path.read_text(encoding="utf-8")

result = parse_character_note(
    text,
    file_path="Story Building/Characters/Lance Irvine.md",
)

pprint(result, sort_dicts=False)
