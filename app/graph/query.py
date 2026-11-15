from app.storage.database import get_connection


def find_entity(name: str) -> dict | None:
    """Find a character by name."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, entity_type, source_path, has_note
            FROM graph_entities
            WHERE name = ? COLLATE NOCASE
            """,
            (name.strip(),),
        ).fetchone()

    return dict(row) if row else None


def get_attributes(name: str) -> list[dict]:
    """Retrieve all known attributes of a character."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                a.attribute_name,
                a.attribute_value,
                a.source_path
            FROM graph_attributes AS a
            JOIN graph_entities AS e
                ON e.id = a.entity_id
            WHERE e.name = ? COLLATE NOCASE
            ORDER BY a.attribute_name
            """,
            (name.strip(),),
        ).fetchall()

    return [dict(row) for row in rows]


def get_relationships(
    name: str,
    direction: str = "both",
) -> list[dict]:
    """
    Retrieve relationships involving a character.

    direction:
        outgoing - relationships declared by this character's note
        incoming - relationships pointing toward this character
        both     - all known connections
    """

    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError("Invalid direction.")

    conditions = {
        "outgoing": "source.name = ? COLLATE NOCASE",
        "incoming": "target.name = ? COLLATE NOCASE",
        "both": """
            (
                source.name = ? COLLATE NOCASE
                OR target.name = ? COLLATE NOCASE
            )
        """,
    }

    with get_connection() as connection:
        if direction == "both":
            rows = connection.execute(
                f"""
                SELECT
                    source.name AS source,
                    target.name AS target,
                    r.relationship_type,
                    r.source_path
                FROM graph_relationships AS r
                JOIN graph_entities AS source
                    ON source.id = r.source_entity_id
                JOIN graph_entities AS target
                    ON target.id = r.target_entity_id
                WHERE {conditions[direction]}
                ORDER BY source.name, target.name
                """,
                (name.strip(), name.strip()),
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT
                    source.name AS source,
                    target.name AS target,
                    r.relationship_type,
                    r.source_path
                FROM graph_relationships AS r
                JOIN graph_entities AS source
                    ON source.id = r.source_entity_id
                JOIN graph_entities AS target
                    ON target.id = r.target_entity_id
                WHERE {conditions[direction]}
                ORDER BY source.name, target.name
                """,
                (name.strip(),),
            ).fetchall()

    return [dict(row) for row in rows]


def get_character_profile(name: str) -> dict | None:
    """Retrieve a character and their known graph information."""
    entity = find_entity(name)

    if entity is None:
        return None

    return {
        "entity": entity,
        "attributes": get_attributes(name),
        "relationships": get_relationships(name),
    }
