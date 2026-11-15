import re
from pathlib import Path


WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def remove_frontmatter(text: str) -> str:
    """Remove YAML frontmatter when it exists."""
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        return text

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1:])

    return text


def parse_character_note(text: str, file_path: str = "") -> dict:
    """
    Extract structured character data from an Obsidian character note.
    This function only reads text; it does not modify any files.
    """
    text = remove_frontmatter(text)

    attributes = {}
    relationships = []
    current_section = None

    for line in text.splitlines():
        if not line.strip():
            continue

        # Detect the Relationship section.
        relationship_match = re.match(
            r"^\s*Relationship\s*:\s*(.*)$",
            line,
            re.IGNORECASE,
        )

        if relationship_match:
            current_section = "relationships"
            remainder = relationship_match.group(1).strip()

            if remainder:
                line = remainder
            else:
                continue

        # Extract relationship entries such as:
        # [[Selene Irvine]] (Spouse)
        if current_section == "relationships":
            links = WIKILINK_PATTERN.findall(line)

            if links:
                label_match = re.search(r"\(([^)]+)\)", line)
                relationships.append({
                    "target": links[0].strip(),
                    "label": label_match.group(1).strip()
                    if label_match else "Unspecified",
                })
                continue

            # A new top-level property ends the relationship section.
            if re.match(r"^\s*[A-Za-z][A-Za-z0-9 _-]*\s*:", line):
                current_section = None
            else:
                continue

        # Extract ordinary key-value attributes.
        attribute_match = re.match(
            r"^\s*([A-Za-z][A-Za-z0-9 _-]*)\s*:\s*(.*?)\s*$",
            line,
        )

        if attribute_match:
            key = attribute_match.group(1).strip()
            value = attribute_match.group(2).strip()

            if key.lower() != "relationship" and value:
                attributes[key] = value

    filename = Path(file_path).stem if file_path else "Unknown"
    character_name = (
    attributes.get("Fullname")
    or attributes.get("Full name")
    or attributes.get("Name")
    or filename)

    return {
        "name": character_name,
        "file": file_path,
        "attributes": attributes,
        "relationships": relationships,
    }
