#!/usr/bin/env python3
"""
Manual ingestion script for local testing.

Usage:
    python scripts/manual_ingest.py --bucket marketing-ai-documents --key path/to/file.pdf
    python scripts/manual_ingest.py --bucket marketing-ai-documents --key path/to/data.csv

Environment variables required:
    DB_HOST, DB_PORT, DB_NAME, AWS_BEDROCK_REGION
    DB_READONLY_SECRET_NAME, DB_APP_SECRET_NAME
    (or set a local .env file and load it before running)
"""
import argparse
import json
import sys

# Ensure the project root is on the Python path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.csv_ingester import ingest_csv
from src.ingestion.pdf_ingester import ingest_pdf


def main():
    parser = argparse.ArgumentParser(description="Manually ingest a PDF or CSV into the RAG pipeline.")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--key", required=True, help="S3 object key (e.g. documents/brochure.pdf)")
    args = parser.parse_args()

    key_lower = args.key.lower()
    if key_lower.endswith(".pdf"):
        print(f"Ingesting PDF: s3://{args.bucket}/{args.key}")
        result = ingest_pdf(args.bucket, args.key)
    elif key_lower.endswith(".csv"):
        print(f"Ingesting CSV: s3://{args.bucket}/{args.key}")
        result = ingest_csv(args.bucket, args.key)
    else:
        print(f"Unsupported file type for key: {args.key}")
        sys.exit(1)

    print(json.dumps(result, indent=2))

    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
