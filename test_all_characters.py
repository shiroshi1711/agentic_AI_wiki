from pathlib import Path

from app.graph.parser import parse_character_note


CHARACTER_DIR = Path(
    "/home/novia/my_obsidian_vault/Story Building/Characters"
)

files = sorted(CHARACTER_DIR.glob("*.md"))

print(f"Found {len(files)} character notes.\n")

total_attributes = 0
total_relationships = 0
issues = []

for file_path in files:
    text = file_path.read_text(encoding="utf-8")

    result = parse_character_note(
        text,
        file_path=str(file_path.relative_to(CHARACTER_DIR.parent.parent)),
    )

    attributes = result["attributes"]
    relationships = result["relationships"]

    total_attributes += len(attributes)
    total_relationships += len(relationships)

    print(f"{result['name']}")
    print(f"   Attributes: {len(attributes)}")
    print(f"   Relationships: {len(relationships)}")

    if not attributes:
        issues.append(f"{file_path.name}: no attributes detected")

    if not any(
    key in attributes
    for key in ("Fullname", "Full name", "Name")):
   	 issues.append(f"{file_path.name}: missing name field")

print("\n========== SUMMARY ==========")
print(f"Characters scanned: {len(files)}")
print(f"Total attributes: {total_attributes}")
print(f"Total relationships: {total_relationships}")

if issues:
    print("\n Potential issues:")
    for issue in issues:
        print(f"- {issue}")
else:
    print("\nNo obvious parsing issues detected.")
