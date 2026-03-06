import json
from typing import Any

from src.db.postgres_client import get_connection

"""
Where are embeddings stored?

In PostgreSQL — specifically the document_embeddings table. See line 23: it does a SQL INSERT INTO document_embeddings. This table uses the pgvector extension, which lets Postgres store and search high-dimensional vectors natively. So the database is doing double duty: regular data AND vector similarity search.
"""

def store_embedding(
    content: str,
    embedding: list[float],
    source_file: str,
    metadata: dict[str, Any],
) -> int:
    """
    Insert a document chunk and its embedding into document_embeddings.
    Returns the new row id.
    """
    conn = get_connection("app")
    try:
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO document_embeddings (content, embedding, source_file, metadata)
                VALUES (%s, %s::vector, %s, %s)
                RETURNING id
                """,
                (content, embedding_str, source_file, json.dumps(metadata)),
            )
            row = cursor.fetchone()
        conn.commit()
        return row["id"]
    finally:
        conn.close()


def similarity_search(query_embedding: list[float], top_k: int = 3) -> list[dict]:
    """
    Perform cosine similarity search using pgvector.
    Returns the top_k most similar chunks as list of dicts with keys:
        id, content, source_file, metadata, similarity
    """
    conn = get_connection("readonly")
    try:
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, content, source_file, metadata,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM document_embeddings
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (embedding_str, embedding_str, top_k),
            )
            return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
