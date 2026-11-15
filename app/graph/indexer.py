from pathlib import Path

from app.graph.parser import parse_character_note
from app.storage.database import get_connection, initialize_database


def index_character_graph(vault_path: Path) -> dict:
    """
    Rebuild the character Knowledge Graph from Obsidian notes.

    This only reads Markdown files. It never modifies the vault.
    """

    vault_path = Path(vault_path).resolve()
    characters_dir = vault_path / "Story Building" / "Characters"

    if not characters_dir.is_dir():
        raise FileNotFoundError(
            f"Character directory not found: {characters_dir}"
        )

    parsed_characters = []

    # Read and parse character notes.
    for file_path in sorted(characters_dir.rglob("*.md")):

        relative_path = file_path.relative_to(vault_path)

        # Ignore hidden directories and files.
        if any(part.startswith(".") for part in relative_path.parts):
            continue

        # Prevent symlinks from escaping the vault.
        if not file_path.resolve().is_relative_to(vault_path):
            continue

        text = file_path.read_text(encoding="utf-8")

        character = parse_character_note(
            text,
            relative_path.as_posix(),
        )

        parsed_characters.append(character)

    initialize_database()

    with get_connection() as connection:

        # This graph currently contains only Character Bible data.
        # Clear old graph records before rebuilding.
        connection.execute("DELETE FROM graph_relationships")
        connection.execute("DELETE FROM graph_attributes")
        connection.execute("DELETE FROM graph_entities")

        # First, create entities for characters with actual notes.
        for character in parsed_characters:
            connection.execute(
                """
                INSERT INTO graph_entities (
                    name,
                    entity_type,
                    source_path,
                    has_note
                )
                VALUES (?, 'character', ?, 1)
                """,
                (
                    character["name"],
                    character["file"],
                ),
            )

        # Create placeholder entities for linked characters
        # who do not yet have their own character note.
        for character in parsed_characters:
            for relationship in character["relationships"]:
                connection.execute(
                    """
                    INSERT INTO graph_entities (
                        name,
                        entity_type,
                        source_path,
                        has_note
                    )
                    VALUES (?, 'character', NULL, 0)
                    ON CONFLICT(name) DO NOTHING
                    """,
                    (relationship["target"],),
                )

        # Store attributes and relationships.
        for character in parsed_characters:

            source = connection.execute(
                """
                SELECT id
                FROM graph_entities
                WHERE name = ?
                """,
                (character["name"],),
            ).fetchone()

            source_id = source["id"]

            for attribute_name, attribute_value in (
                character["attributes"].items()
            ):
                connection.execute(
                    """
                    INSERT INTO graph_attributes (
                        entity_id,
                        attribute_name,
                        attribute_value,
                        source_path
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        attribute_name,
                        attribute_value,
                        character["file"],
                    ),
                )

            for relationship in character["relationships"]:

                target = connection.execute(
                    """
                    SELECT id
                    FROM graph_entities
                    WHERE name = ?
                    """,
                    (relationship["target"],),
                ).fetchone()

                connection.execute(
                    """
                    INSERT INTO graph_relationships (
                        source_entity_id,
                        target_entity_id,
                        relationship_type,
                        source_path
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        target["id"],
                        relationship["label"],
                        character["file"],
                    ),
                )

        entity_count = connection.execute(
            "SELECT COUNT(*) FROM graph_entities"
        ).fetchone()[0]

        attribute_count = connection.execute(
            "SELECT COUNT(*) FROM graph_attributes"
        ).fetchone()[0]

        relationship_count = connection.execute(
            "SELECT COUNT(*) FROM graph_relationships"
        ).fetchone()[0]

    return {
        "characters_parsed": len(parsed_characters),
        "entities": entity_count,
        "attributes": attribute_count,
        "relationships": relationship_count,
    }
