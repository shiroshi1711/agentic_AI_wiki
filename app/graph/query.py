from app.storage.database import get_connection

def interpret_relationship(
    source: str,
    target: str,
    relationship: str,
) -> str:
    """Interpret a relationship from the note owner's perspective."""

    label = relationship.strip().casefold()

    if label == "father":
        return f"{target} is the father of {source}."

    if label == "mother":
        return f"{target} is the mother of {source}."

    if label == "older sibling":
        return f"{target} is the older sibling of {source}."

    if label == "younger sibling":
        return f"{target} is the younger sibling of {source}."

    if label == "firstborn child":
        return f"{target} is the firstborn child of {source}."

    if label in {"close friend", "childhood friend", "academy close friend"}:
        return f"{target} is a {label} of {source}."

    if label in {"spouse", "romantic partner"}:
        return f"{target} is the {label} of {source}."

    return (
        f"{source} identifies {target} as: "
        f"{relationship}. Meaning not yet defined."
    )

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

def get_connected_characters(
    name: str,
    max_depth: int = 1,
) -> list[dict]:
    """
    Explore characters connected to a starting character.

    max_depth controls how many relationship steps to follow.
    """

    if not 1 <= max_depth <= 3:
        raise ValueError("max_depth must be between 1 and 3.")

    visited = {name.strip().casefold()}
    frontier = [name.strip()]
    results = []

    for depth in range(1, max_depth + 1):
        next_frontier = []

        for current_name in frontier:
            relationships = get_relationships(
                current_name,
                direction="both",
            )

            for relationship in relationships:
                source = relationship["source"]
                target = relationship["target"]

                connected_name = (
                    target
                    if source.casefold() == current_name.casefold()
                    else source
                )

                key = connected_name.casefold()

                if key in visited:
                    continue

                visited.add(key)

                entity = find_entity(connected_name)

                if entity is None:
                    continue

                results.append({
                    "name": connected_name,
                    "depth": depth,
                    "relationship": relationship["relationship_type"],
                    "source": relationship["source"],
                    "target": relationship["target"],
                    "interpretation": interpret_relationship(
                        relationship["source"],
                        relationship["target"],
                        relationship["relationship_type"],
                    ),
                    "source_path": relationship["source_path"],
                    "entity": entity,
                })

                next_frontier.append(connected_name)

        frontier = next_frontier

        if not frontier:
            break

    return results
