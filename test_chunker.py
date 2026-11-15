from app.retrieval.chunker import chunk_text


sample = """
# Prince Arven

Arven was born in the northern kingdom of Elaria.
His mother died when he was very young.

## Childhood

His grandmother raised him inside the royal palace.
She taught him history, diplomacy, and swordsmanship.

## The Great War

When Arven turned sixteen, the northern kingdom
was invaded by the armies of the Ashen Empire.
"""

chunks = chunk_text(sample)

print(f"Total chunks: {len(chunks)}")

for number, chunk in enumerate(chunks, start=1):
    print(f"\n--- Chunk {number} ({len(chunk)} characters) ---")
    print(chunk)
