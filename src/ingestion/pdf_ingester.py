"""
PDF Ingestion pipeline.

Downloads a PDF from S3, splits it into chunks, embeds each chunk via
AWS Bedrock Titan, and stores the results in document_embeddings.
"""
import io
import json
import logging
import os
from datetime import datetime, timezone

from langchain.text_splitter import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from src.db.vector_store import store_embedding
from src.utils.bedrock_client import get_embeddings
from src.utils.s3_client import download_file

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def ingest_pdf(bucket: str, key: str) -> dict:
    """
    Ingest a PDF from S3.

    1. Download the PDF bytes from S3.
    2. Extract text using PyPDF.
    3. Split into chunks (500 tokens, 50 overlap).
    4. Embed each chunk via Bedrock Titan.
    5. Store embeddings in document_embeddings table.

    Returns a summary dict with chunk_count and status.
    """
    logger.info(json.dumps({"event": "pdf_ingest_start", "bucket": bucket, "key": key,
                             "timestamp": datetime.now(timezone.utc).isoformat()}))

    # 1. Download
    pdf_bytes = download_file(bucket, key)

    # 2. Extract text
    reader = PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )

    if not full_text.strip():
        logger.warning(json.dumps({"event": "pdf_ingest_empty", "key": key}))
        return {"status": "skipped", "reason": "empty text", "chunk_count": 0}

    # 3. Chunk
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_text(full_text)

    # 4 & 5. Embed and store
    embeddings_client = get_embeddings()
    stored_ids = []
    for i, chunk in enumerate(chunks):
        embedding = embeddings_client.embed_query(chunk)
        chunk_metadata = {
            "chunk_index": i,
            "total_chunks": len(chunks),
            "source_bucket": bucket,
        }
        row_id = store_embedding(
            content=chunk,
            embedding=embedding,
            source_file=key,
            metadata=chunk_metadata,
        )
        stored_ids.append(row_id)

    logger.info(json.dumps({
        "event": "pdf_ingest_complete",
        "key": key,
        "chunk_count": len(chunks),
        "stored_ids": stored_ids,
    }))

    return {"status": "success", "chunk_count": len(chunks), "stored_ids": stored_ids}
