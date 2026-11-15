from pprint import pprint

from app.graph.context import retrieve_graph_context


queries = [
    "Tell me about Lance Irvine.",
    "Who is Lance Irvine married to?",
    "What are Lance Irvine's relationships?",
    "Tell me about an unknown character.",
]

for query in queries:
    print(f"\n=== QUERY: {query} ===")

    context, sources = retrieve_graph_context(query)

    print("\nGRAPH CONTEXT:")
    print(context or "No graph information found.")

    print("\nSOURCES:")
    pprint(sources)
