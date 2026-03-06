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
    # PdfReader expects to receive something that behaves like an open file — it needs to be able to seek, read forward, etc. But pdf_bytes is just raw bytes in memory, not a file. io.BytesIO(pdf_bytes) wraps those raw bytes in a fake file object that behaves exactly like an open file. It's a bridge: "pretend these bytes are a file." Think of it like wrapping a Buffer in a Readable stream in Node.
    reader = PdfReader(io.BytesIO(pdf_bytes))
    # reader.pages — a list of page objects, one per page in the PDF. Like [page1, page2, page3, ...]
    # for page in reader.pages — loop over every page. Same as for (const page of reader.pages) in TS.
    # page.extract_text() — reads all the text off one page. Returns a string, or None if the page has no readable text (e.g. a scanned image).
    # or "" — if extract_text() returned None, use an empty string instead. This is Python's short-circuit: None or "" → "". Same as page.extract_text() ?? "" in TS.
    # "\n".join(...) — takes all those page strings and glues them together with a newline between each one. TS equivalent: pageTexts.join("\n")
    # Net result: every page's text, separated by a newline, all in one big string called full_text.
    # full_text is a huge string containing all the text from the PDF
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # .strip() only removes leading and trailing whitespace from the outer edges of the entire string. It does not touch anything in the middle. Is asking: "after trimming edges, is there anything left at all?". 
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
    # Why do we need stored_ids at all?
    # Honestly — for logging/tracing only. Look at line 82 — it's included in the success log message. That's it. No code uses stored_ids for anything functional after the log.
    # If something goes wrong during ingestion, you can go to CloudWatch, find the log line, see the exact list of DB row IDs that were written, and cross-reference them directly in the database. It's a debugging aid, not a functional requirement.
    stored_ids = []
    for i, chunk in enumerate(chunks):
        embedding = embeddings_client.embed_query(chunk)
        chunk_metadata = {
            "chunk_index": i,
            "total_chunks": len(chunks),
            "source_bucket": bucket,
        }
        """
        What does store_embedding return and why row_id?
        Look at lines 25–31. After the INSERT (vector_story.py), it runs RETURNING id — that's a Postgres feature that says "after inserting, give me back the id column of the new row." So store_embedding returns the auto-generated integer ID of the row that was just created in the DB. That integer gets saved in row_id, then appended to stored_ids in pdf_ingester.py. One ID per chunk.
        """
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
