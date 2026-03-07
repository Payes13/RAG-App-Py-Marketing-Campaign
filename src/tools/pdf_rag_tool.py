"""
Tool 2: Semantic search over PDF embeddings stored in pgvector.

Embeds the user's question via Bedrock Titan and retrieves the top 3
most relevant document chunks from document_embeddings.
"""
import json
import logging

from langchain.tools import tool

from src.db.vector_store import similarity_search
from src.utils.bedrock_client import get_embeddings

logger = logging.getLogger(__name__)

# Shared metadata collector — populated during tool execution
_rag_metadata: dict = {
    "rag_chunks": [],
}

def reset_rag_metadata():
    _rag_metadata["rag_chunks"] = []

def get_rag_metadata() -> dict:
    return _rag_metadata

@tool
def search_campaign_documents(question: str) -> str:
    """Use this tool when you need context about previous marketing campaigns,
    destination descriptions, or marketing strategies from PDF documents."""
    try:
        embeddings_client = get_embeddings()
        query_embedding = embeddings_client.embed_query(question)

        chunks = similarity_search(query_embedding, top_k=3)

        logger.info(json.dumps({
            "event": "rag_search",
            "question": question,
            "chunks_found": len(chunks),
        }))

        if not chunks:
            return "No relevant documents found."

        # Track metadata
        for chunk in chunks:
            _rag_metadata["rag_chunks"].append({
                "source_file": chunk.get("source_file"),
                "content_excerpt": chunk.get("content", "")[:200],
                "similarity": chunk.get("similarity"),
            })

        # Format for LLM consumption
        result_parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source_file", "unknown")
            content = chunk.get("content", "")
            similarity = chunk.get("similarity", 0)
            # .3f = 3 decimal places
            # ["[Document 1 — policy.pdf (similarity: 0.923)]\nEmployees must submit expenses within 30 days."]
            result_parts.append(
                f"[Document {i} — {source} (similarity: {similarity:.3f})]\n{content}"
            )

        """
        [Document 1 — policy.pdf (similarity: 0.923)]
        Employees must submit expenses within 30 days.

        ---

        [Document 2 — handbook.pdf (similarity: 0.813)]
        Vacation requests must be approved by managers.
        """
        return "\n\n---\n\n".join(result_parts)

    except Exception as exc:
        logger.error(json.dumps({"event": "rag_tool_error", "error": str(exc)}))
        return f"Error retrieving documents: {exc}"
