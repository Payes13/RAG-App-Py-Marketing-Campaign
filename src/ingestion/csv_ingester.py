"""
CSV Ingestion pipeline.

Downloads a CSV from S3, validates its format, and stores metadata
in the csv_files table for later reference by the CSV analyzer tool.
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
        df = pd.read_csv(io.BytesIO(csv_bytes))
    except Exception as exc:
        logger.error(json.dumps({"event": "csv_ingest_parse_error", "key": key, "error": str(exc)}))
        return {"status": "error", "reason": f"CSV parse error: {exc}"}

    if df.empty:
        logger.warning(json.dumps({"event": "csv_ingest_empty", "key": key}))
        return {"status": "skipped", "reason": "empty CSV", "row_count": 0}

    column_names = df.columns.tolist()
    row_count = len(df)

    # 2. Store metadata
    conn = get_connection("app")
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
