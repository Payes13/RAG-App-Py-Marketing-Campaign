"""
Security audit logging (Layer 5) and column-level masking.

All query attempts — allowed or rejected — are logged to CloudWatch (stdout in Lambda).
Sensitive fields (email, name) are masked in logs and the metadata PDF.
The actual data passed to the LLM is never masked.
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional

FIELDS_TO_MASK_IN_LOGS = ["email", "name"]


def _mask_email(email: str) -> str:
    """carlos.mendoza@email.com → car***@***.com"""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked_local = local[:3] + "***" if len(local) > 3 else "***"
    domain_parts = domain.split(".")
    masked_domain = "***." + domain_parts[-1] if domain_parts else "***"
    return f"{masked_local}@{masked_domain}"


def _mask_name(name: str) -> str:
    """Carlos Mendoza → C*** M***"""
    parts = name.split()
    return " ".join(p[0] + "***" if p else "***" for p in parts)


def mask_row(row: dict) -> dict:
    """
    Return a copy of the row dict with sensitive fields masked.
    Used only for logs and metadata PDF — never for LLM input.
    """
    masked = dict(row)
    for key, value in masked.items():
        if key.lower() == "email" and isinstance(value, str):
            masked[key] = _mask_email(value)
        elif key.lower() == "name" and isinstance(value, str):
            masked[key] = _mask_name(value)
    return masked


def log_query_event(
    event_type: str,
    status: str,
    sql: str,
    tables: list[str],
    exec_time_ms: int,
    rows: int,
    request_id: str,
    rejection_layer: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> None:
    """
    Write a structured CloudWatch audit log for every query attempt.
    In Lambda, stdout is automatically forwarded to CloudWatch Logs.
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "status": status,
        "rejection_layer": rejection_layer,
        "rejection_reason": rejection_reason,
        "generated_sql": sql,
        "tables_accessed": tables,
        "execution_time_ms": exec_time_ms,
        "rows_returned": rows,
        "lambda_request_id": request_id,
    }
    print(json.dumps(log_entry))
