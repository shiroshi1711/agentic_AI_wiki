import json
from pathlib import Path

from app.config.settings import get_settings
from app.llm.embeddings import generate_embeddings
from app.retrieval.chunker import chunk_text
from app.storage.database import get_connection, initialize_database


BATCH_SIZE = 16


async def index_vault_semantic() -> int:
    vault = get_settings().vault_path.resolve()

    if not vault.is_dir():
        raise FileNotFoundError(f"Vault directory not found: {vault}")

    initialize_database()

    # Collect all chunks before changing the existing semantic index.
    pending_chunks = []

    for file_path in vault.rglob("*.md"):
        relative_path = file_path.relative_to(vault)

        # Ignore hidden directories and files.
        if any(part.startswith(".") for part in relative_path.parts):
            continue

        resolved_path = file_path.resolve()

        # Prevent symlinks from escaping the vault.
        if not resolved_path.is_relative_to(vault):
            continue

        try:
            content = resolved_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        chunks = chunk_text(content)

        for chunk_index, chunk in enumerate(chunks):
            pending_chunks.append({
                "path": relative_path.as_posix(),
                "chunk_index": chunk_index,
                "content": chunk,
            })

    if not pending_chunks:
        with get_connection() as connection:
            connection.execute("DELETE FROM note_chunks")
        return 0

    # Generate embeddings in manageable batches.
    records = []

    for start in range(0, len(pending_chunks), BATCH_SIZE):
        batch = pending_chunks[start:start + BATCH_SIZE]
        # Each chunk is embedded WITH its note's title and folder. A chunk from
        # the middle of "The Sundering" may never say "Sundering"; without this
        # label its meaning-numbers could not tell which event it belongs to.
        texts = [
            f"Note: {Path(item['path']).stem} (folder: {Path(item['path']).parent.as_posix()})\n\n"
            + item["content"]
            for item in batch
        ]

        embeddings = await generate_embeddings(texts)

        if len(embeddings) != len(batch):
            raise RuntimeError("Embedding count does not match chunk count.")

        for item, embedding in zip(batch, embeddings):
            records.append((
                item["path"],
                item["chunk_index"],
                item["content"],
                json.dumps(embedding),
            ))

        print(f"Embedded {len(records)} / {len(pending_chunks)} chunks")

    # Replace the index only after every embedding was generated successfully.
    with get_connection() as connection:
        connection.execute("DELETE FROM note_chunks")

        connection.executemany(
            """
            INSERT INTO note_chunks (
                path,
                chunk_index,
                content,
                embedding_json
            )
            VALUES (?, ?, ?, ?)
            """,
            records,
        )

    return len(records)
