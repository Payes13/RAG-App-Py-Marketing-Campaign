"""
Lambda handler: S3 Event Trigger for document ingestion.

Triggered automatically when a new file is uploaded to the input S3 bucket.
- .pdf files  → chunk → embed → store in document_embeddings
- .csv files  → validate → store metadata in csv_files table
"""
import json
import logging
from datetime import datetime, timezone

from src.ingestion.csv_ingester import ingest_csv
from src.ingestion.pdf_ingester import ingest_pdf

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def handler(event: dict, context) -> dict:
    request_id = getattr(context, "aws_request_id", "local")
    results = []

    records = event.get("Records", [])
    logger.info(json.dumps({
        "event": "ingestion_handler_start",
        "record_count": len(records),
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    for record in records:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        logger.info(json.dumps({
            "event": "ingestion_record",
            "bucket": bucket,
            "key": key,
        }))

        try:
            key_lower = key.lower()
            if key_lower.endswith(".pdf"):
                result = ingest_pdf(bucket, key)
                results.append({"key": key, "type": "pdf", **result})
            elif key_lower.endswith(".csv"):
                result = ingest_csv(bucket, key)
                results.append({"key": key, "type": "csv", **result})
            else:
                logger.warning(json.dumps({"event": "unsupported_file_type", "key": key}))
                results.append({"key": key, "type": "unknown", "status": "skipped",
                                 "reason": "Unsupported file type"})

        except Exception as exc:
            logger.error(json.dumps({
                "event": "ingestion_error",
                "key": key,
                "error": str(exc),
            }))
            results.append({"key": key, "status": "error", "error": str(exc)})

    logger.info(json.dumps({
        "event": "ingestion_handler_complete",
        "results": results,
        "request_id": request_id,
    }))

    return {"statusCode": 200, "body": json.dumps(results)}
