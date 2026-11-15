from pathlib import Path

from app.graph.indexer import index_character_graph


vault_path = Path.home() / "my_obsidian_vault"

result = index_character_graph(vault_path)

print("Knowledge Graph indexing complete!")
print(result)
