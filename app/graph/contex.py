import re

from app.graph.query import (
    get_attributes,
    get_relationships,
    find_entity,
)


def retrieve_graph_context(
    query: str,
    max_entities: int = 3,
) -> tuple[str, list[str]]:
    """
    Find character entities mentioned in a query and
    retrieve their attributes and relationships.
    """

    from app.storage.database import get_connection

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT name
            FROM graph_entities
            WHERE has_note = 1
            ORDER BY LENGTH(name) DESC
        """).fetchall()

    matched_names = []

    for row in rows:
        name = row["name"]

        pattern = (
            r"(?<!\w)"
            + re.escape(name)
            + r"(?!\w)"
        )

        if re.search(pattern, query, re.IGNORECASE):
            matched_names.append(name)

        if len(matched_names) >= max_entities:
            break

    if not matched_names:
        return "", []

    context_parts = []
    sources = []

    for name in matched_names:
        entity = find_entity(name)

        if entity is None:
            continue

        context_parts.append(f"CHARACTER: {entity['name']}")

        attributes = get_attributes(name)

        if attributes:
            context_parts.append("Attributes:")

            for attribute in attributes:
                context_parts.append(
                    f"- {attribute['attribute_name']}: "
                    f"{attribute['attribute_value']}"
                )

                sources.append(attribute["source_path"])

        relationships = get_relationships(name, direction="both")

        if relationships:
            context_parts.append("Recorded relationships:")

            for relationship in relationships:
                if relationship["source"].casefold() == name.casefold():
                    description = (
                        f"{relationship['source']} -> "
                        f"{relationship['target']}"
                    )
                else:
                    description = (
                        f"{relationship['source']} -> "
                        f"{relationship['target']} "
                        f"(points toward {name})"
                    )

                context_parts.append(
                    f"- {description}: "
                    f"{relationship['relationship_type']}"
                )

                sources.append(relationship["source_path"])

        if entity["source_path"]:
            sources.append(entity["source_path"])

        context_parts.append("")

    return (
        "\n".join(context_parts).strip(),
        list(dict.fromkeys(sources)),
    )
