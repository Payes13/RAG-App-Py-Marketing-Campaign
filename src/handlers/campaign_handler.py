"""
Lambda handler: POST /campaign/generate

Orchestrates the full campaign generation flow:
1. Validate user input (prompt injection guard)
2. Run the ReAct agent (SQL + RAG + CSV tools)
3. Generate campaign and metadata PDFs in memory
4. Upload PDFs to S3
5. Log campaign to generated_campaigns table
6. Return HTTP 200 with campaign content and file URIs
"""
import json
import logging
import os
from datetime import datetime, timezone

from src.agents.marketing_agent import run_marketing_agent
from src.db.postgres_client import get_connection
from src.output.pdf_generator import generate_campaign_pdf, generate_metadata_pdf
from src.output.s3_uploader import upload_campaign_pdfs
from src.security.prompt_guard import check_user_input

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }

def _log_campaign_to_db(metadata: dict, campaign_key: str, metadata_key: str) -> None:
    conn = get_connection("app")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO generated_campaigns
                    (campaign_file_key, metadata_file_key, route, audience_description,
                     campaign_type, language, tokens_used, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    campaign_key,
                    metadata_key,
                    metadata.get("route"),
                    metadata.get("audience_description"),
                    metadata.get("campaign_type"),
                    metadata.get("language"),
                    metadata.get("tokens_used", 0),
                    metadata.get("generated_at"),
                ),
            )
        conn.commit()
    finally:
        conn.close()

def handler(event: dict, context) -> dict:
    request_id = getattr(context, "aws_request_id", "local")
    logger.info(json.dumps({
        "event": "handler_start",
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    # Parse request body
    try:
        body = json.loads(event.get("body", "{}") or "{}")
    except (json.JSONDecodeError, TypeError) as exc:
        return _response(400, {"error": f"Invalid JSON body: {exc}"})

    # Required fields
    required = ["route", "audience_description", "campaign_type", "language", "tone"]
    # for each field name f in required, include it in missing if body.get(f) is falsy. body.get(f) returns None if the key isn't in the dict (no KeyError). not body.get(f) is True when the value is None, "", 0, or simply absent. The result is a list of every required key that the caller forgot to send (or sent empty).
    """
    So the order per iteration is:
    f gets the next string from required
    body.get(f) is evaluated — did the caller send this field?
    not body.get(f) — is it missing/empty?
    If true (missing) → first f is collected into missing
    If false (present) → first f is skipped
    """
    missing = [f for f in required if not body.get(f)]
    if missing:
        return _response(400, {"error": f"Missing required fields: {missing}"})

    route = body["route"]
    audience_description = body["audience_description"]
    campaign_type = body["campaign_type"]
    language = body["language"]
    tone = body["tone"]
    csv_file_key = body.get("csv_file_key", "")

    # Layer 6: Prompt injection guard
    # tuple unpacking: The list contains tuples — pairs of (name, value). On each iteration Python automatically unpacks the pair into two variables. It's equivalent to:
    # what Python does internally each iteration:
    # (field_name, value) = ("route", route)
    # → field_name = "route", value = "Montreal-San Salvador"
    # Why is language (and campaign_type) left out of the injection check?. Because language and campaign_type are expected to be short controlled values — think "en", "fr", "promotional". There's almost no attack surface in a 2-letter language code. The fields that ARE checked are the ones where a user types free-form text — a route name, a description of their audience, a tone — any of which could contain something like "Ignore previous instructions and...". That's where injection lives.
    for field_name, value in [
        ("route", route),
        ("audience_description", audience_description),
        ("tone", tone),
        ("csv_file_key", csv_file_key),
    ]:
        is_clean, reason = check_user_input(value)
        if not is_clean:
            logger.warning(json.dumps({"event": "prompt_injection_blocked", "field": field_name}))
            return _response(400, {"error": reason})

    # Run agent and generate campaign
    try:
        result = run_marketing_agent(
            route=route,
            audience_description=audience_description,
            campaign_type=campaign_type,
            language=language,
            tone=tone,
            csv_file_key=csv_file_key,
            request_id=request_id,
        )
    except ValueError as exc:
        logger.error(json.dumps({"event": "agent_error", "error": str(exc)}))
        return _response(400, {"error": str(exc)})
    except Exception as exc:
        logger.error(json.dumps({"event": "agent_unexpected_error", "error": str(exc)}))
        return _response(500, {"error": "Internal error during campaign generation"})

    campaign = result["campaign"]
    metadata = result["metadata"]

    # Generate PDFs in memory
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    generated_at = metadata.get("generated_at", datetime.now(timezone.utc).isoformat())

    try:
        campaign_pdf = generate_campaign_pdf(campaign, route, generated_at)
        metadata_pdf = generate_metadata_pdf(metadata)
    except Exception as exc:
        logger.error(json.dumps({"event": "pdf_generation_error", "error": str(exc)}))
        return _response(500, {"error": "Failed to generate PDF output"})

    # Upload to S3 (non-blocking failure: still return campaign JSON)
    output_files = {}
    try:
        output_files = upload_campaign_pdfs(campaign_pdf, metadata_pdf, route, today)
    except Exception as exc:
        logger.error(json.dumps({"event": "s3_upload_error", "error": str(exc)}))
        output_files = {
            "campaign_pdf": "upload_failed",
            "metadata_pdf": "upload_failed",
            "warning": str(exc),
        }

    # Log to database
    try:
        campaign_key = output_files.get("campaign_pdf", "").replace(
            f"s3://{os.environ.get('S3_OUTPUT_BUCKET_NAME', '')}/", ""
        )
        metadata_key = output_files.get("metadata_pdf", "").replace(
            f"s3://{os.environ.get('S3_OUTPUT_BUCKET_NAME', '')}/", ""
        )
        _log_campaign_to_db(metadata, campaign_key, metadata_key)
    except Exception as exc:
        logger.error(json.dumps({"event": "db_log_error", "error": str(exc)}))

    return _response(200, {
        "campaign": campaign,
        "output_files": output_files,
        "audience_size": metadata.get("audience_size", 0),
        "tokens_used": metadata.get("tokens_used", 0),
        "generated_at": generated_at,
    })
