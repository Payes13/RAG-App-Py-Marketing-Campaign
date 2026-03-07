"""
CSV Ingestion pipeline.

Downloads a CSV from S3, validates its format, and stores metadata
in the csv_files table for later reference by the CSV analyzer tool.
"""

"""
                        PDF	                      CSV
Content stored in DB?	Yes — chunked and       No — stays in S3
                        embedded as vectors	
How it's queried later	Vector similarity       Downloaded fresh from S3 
                        search via pgvector	    and analyzed by the LLM
"""
import io
import json
import logging
from datetime import datetime, timezone

import pandas as pd

from src.db.postgres_client import get_connection
from src.utils.s3_client import download_file

logger = logging.getLogger(__name__)

def ingest_csv(bucket: str, key: str) -> dict:
    """
    Ingest a CSV from S3.

    1. Download the CSV bytes from S3.
    2. Validate it can be parsed as a DataFrame.
    3. Store metadata (column names, row count) in the csv_files table.

    Returns a summary dict with row_count, column_count, and status.
    """
    logger.info(json.dumps({"event": "csv_ingest_start", "bucket": bucket, "key": key,
                             "timestamp": datetime.now(timezone.utc).isoformat()}))

    # 1. Download and parse
    csv_bytes = download_file(bucket, key)
    try:
        # pd.read_csv() also expects a file-like object, not raw bytes. So io.BytesIO(csv_bytes) is doing the identical bridge as in pdf_ingester.py — wrapping raw bytes into a fake file so the library can read it. Same pattern, different consumer.
        # .read_csv: parses the raw CSV bytes into a structured DataFrame in one call.
        df = pd.read_csv(io.BytesIO(csv_bytes))
    except Exception as exc:
        logger.error(json.dumps({"event": "csv_ingest_parse_error", "key": key, "error": str(exc)}))
        return {"status": "error", "reason": f"CSV parse error: {exc}"}

    # Check if DataFrame is empty. Checks if the ingested DataFrame has zero rows after parsing CSV.
    if df.empty:
        logger.warning(json.dumps({"event": "csv_ingest_empty", "key": key}))
        return {"status": "skipped", "reason": "empty CSV", "row_count": 0}

    # .columns.tolist() → extracts the column names as a list
    column_names = df.columns.tolist()
    # len(df) → row count
    row_count = len(df)

    # 2. Store metadata
    conn = get_connection("app")
    # THIS QUERY ONLY STORES: s3_key, column_names, row_count, ingested_at
    # The actual data is intentionally NOT stored in the DB. It stays in S3.
    """
    The csv_files table is just a registry — it tells the agent "these CSV files exist, and here are their column names." That metadata is enough for the agent to know which file is relevant to a question.

    When the agent actually needs to analyze a CSV, the csv_analyzer_tool downloads the full file directly from S3 at query time and feeds it to the LLM. You'll see this when you get to src/tools/csv_analyzer_tool.py.

    The reason CSVs aren't embedded like PDFs: CSVs contain structured numerical/tabular data that a LLM analyzes better by seeing the actual rows, not by searching for similar text chunks. PDFs are unstructured prose — vector search makes sense for those.
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO csv_files (s3_key, column_names, row_count, ingested_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (s3_key) DO UPDATE
                    SET column_names = EXCLUDED.column_names,
                        row_count = EXCLUDED.row_count,
                        ingested_at = EXCLUDED.ingested_at
                """,
                (key, json.dumps(column_names), row_count,
                 datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()
    finally:
        conn.close()

    logger.info(json.dumps({
        "event": "csv_ingest_complete",
        "key": key,
        "row_count": row_count,
        "column_count": len(column_names),
        "columns": column_names,
    }))

    return {
        "status": "success",
        "row_count": row_count,
        "column_count": len(column_names),
        "columns": column_names,
    }
