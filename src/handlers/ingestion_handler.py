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

"""
WHY DO WE NEED A LOGGER?
Python does have print() — it's exactly like console.log. And in Lambda, print() also shows up in CloudWatch automatically. So technically you could use print() everywhere and still see the output.

The reason to use a proper logger instead:
Log levels — you can filter CloudWatch to show only ERROR lines when debugging a production issue, ignoring all the INFO noise
Structured JSON — this code logs JSON objects (see line 42), which CloudWatch can query and filter on specific fields like request_id or event
Named source — each log line automatically includes which module it came from
Production control — you can set level=WARNING in production to silence all info logs without changing code
print() just dumps raw text with no level, no source, no filtering. It works but it's harder to manage at scale.
"""

"""
This creates a logger named after this file. __name__ is a Python built-in that automatically resolves to the module's full name — here it would be "src.handlers.ingestion_handler". So when this logger writes a message, you can tell exactly which file it came from. getLogger(__name__) — creates a named logger for this specific file to use

In TypeScript terms: const logger = new Logger("src/handlers/ingestion_handler")
"""
logger = logging.getLogger(__name__)
"""
This configures the global logging system — it sets the minimum severity level to INFO. Messages at INFO, WARNING, and ERROR will be shown. DEBUG messages will be silently ignored.
The levels from lowest to highest are: DEBUG → INFO → WARNING → ERROR → CRITICAL. basicConfig(level=INFO) — configures the global logging system (only needs to be called once anywhere in the app)

does NOT set the level on that logger. It configures the global/root logging system. Think of it as the master switch for the entire app, not just this file.
"""
logging.basicConfig(level=logging.INFO)

def handler(event: dict, context) -> dict:
    # getattr is Python's way of safely reading a property from an object when you're not sure the property exists.
    # It takes 3 arguments:
    # The object to read from
    # The property name as a string
    # A default value if the property doesn't exist
    # The context object is provided by AWS Lambda at runtime and always has aws_request_id on it. But when you're running the code locally for testing, there's no real Lambda context — you might pass a fake object or None. If the code did context.aws_request_id directly and context was a mock without that property, it would crash.

    # request_id Is a unique ID AWS assigns to each Lambda invocation — like a transaction ID. Every log line in this handler includes it (see lines 41, 64). Why: when multiple files are ingested at the same time, CloudWatch will have log lines from different executions mixed together. The request_id lets you filter all logs from one specific run to trace exactly what happened. Without it, debugging a failure in production would be nearly impossible.
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
                # ** is the dictionary unpacking operator. It takes all the key-value pairs from a dict and spreads them inline into another dict. 
                """
                result is what ingest_pdf returned — a dict like:
                {"status": "success", "chunk_count": 42, "stored_ids": [1, 2, 3]}
                The **result spreads that into the outer dict, so the final object becomes:
                {
                "key": "reports/q1-2026.pdf",
                "type": "pdf",
                "status": "success",
                "chunk_count": 42,
                "stored_ids": [1, 2, 3]
                }
                In TypeScript this is the exact equivalent of the spread operator:
                { key, type: "pdf", ...result }
                Same concept, different syntax — ** in Python, ... in TypeScript.
                """
                results.append({"key": key, "type": "pdf", **result})
            elif key_lower.endswith(".csv"):
                result = ingest_csv(bucket, key)
                results.append({"key": key, "type": "csv", **result})
            else:
                logger.warning(json.dumps({"event": "unsupported_file_type", "key": key}))
                results.append({"key": key, "type": "unknown", "status": "skipped", "reason": "Unsupported file type"})

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
