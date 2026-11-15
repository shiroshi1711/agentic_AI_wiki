from app.tools.search import search_vault
from app.retrieval.semantic_search import semantic_search


def reciprocal_rank_fusion(
    keyword_results: list[dict],
    semantic_results: list[dict],
    limit: int = 5,
    k: int = 60,
) -> list[dict]:

    combined = {}

    def add_result(result: dict, rank: int, source: str):
        path = result["file"]

        if path not in combined:
            combined[path] = {
                "file": path,
                "score": 0.0,
                "sources": [],
            }

        combined[path]["score"] += 1 / (k + rank)

        if source not in combined[path]["sources"]:
            combined[path]["sources"].append(source)

    for rank, result in enumerate(keyword_results, start=1):
        add_result(result, rank, "keyword")

    for rank, result in enumerate(semantic_results, start=1):
        add_result(result, rank, "semantic")

    return sorted(
        combined.values(),
        key=lambda item: item["score"],
        reverse=True,
    )[:limit]


async def hybrid_search(
    query: str,
    limit: int = 5,
) -> list[dict]:

    keyword_results = search_vault(query, limit=limit * 2)

    semantic_results = await semantic_search(
        query,
        limit=limit * 2,
    )

    return reciprocal_rank_fusion(
        keyword_results,
        semantic_results,
        limit=limit,
    )
