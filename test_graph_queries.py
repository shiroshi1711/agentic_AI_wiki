from pprint import pprint

from app.graph.query import (
    find_entity,
    get_attributes,
    get_relationships,
    get_character_profile,
)


character = "Lance Irvine"

print("\n=== FIND CHARACTER ===")
pprint(find_entity(character))

print("\n=== CHARACTER ATTRIBUTES ===")
pprint(get_attributes(character))

print("\n=== OUTGOING RELATIONSHIPS ===")
pprint(get_relationships(character, "outgoing"))

print("\n=== INCOMING RELATIONSHIPS ===")
pprint(get_relationships(character, "incoming"))

print("\n=== COMPLETE CHARACTER PROFILE ===")
pprint(get_character_profile(character))
