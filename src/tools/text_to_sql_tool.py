"""
Tool 1: Text-to-SQL over PostgreSQL.

Translates a natural language question to SQL, validates it through
all security layers, executes it using the read-only DB user, and
returns the results as a formatted string.
"""
import json
import logging
import time
from typing import Any

import psycopg2
from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from src.db.postgres_client import get_connection, execute_query
from src.security.query_logger import log_query_event, mask_row
from src.security.sql_validator import validate_sql
from src.utils.bedrock_client import get_llm

logger = logging.getLogger(__name__)

DB_SCHEMA = """
-- Customer data
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    age INTEGER,
    city VARCHAR(100),
    country VARCHAR(100),
    language VARCHAR(50)
);

-- Flight history
CREATE TABLE flights (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    route VARCHAR(100),
    origin VARCHAR(100),
    destination VARCHAR(100),
    flight_date DATE,
    travel_class VARCHAR(50)
);

-- Customer preferences
CREATE TABLE preferences (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    seat_type VARCHAR(50),
    meal_type VARCHAR(50),
    travel_frequency VARCHAR(50),
    family_size INTEGER
);

-- PDF embeddings
CREATE TABLE document_embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT,
    source_file VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Generated campaigns log
CREATE TABLE generated_campaigns (
    id SERIAL PRIMARY KEY,
    campaign_file_key VARCHAR(255),
    metadata_file_key VARCHAR(255),
    route VARCHAR(100),
    audience_description TEXT,
    campaign_type VARCHAR(50),
    language VARCHAR(10),
    tokens_used INTEGER,
    generated_at TIMESTAMP DEFAULT NOW()
);

-- CSV file metadata
CREATE TABLE csv_files (
    id SERIAL PRIMARY KEY,
    s3_key VARCHAR(500) UNIQUE,
    column_names JSONB,
    row_count INTEGER,
    ingested_at TIMESTAMP DEFAULT NOW()
);
"""

_SQL_SYSTEM_PROMPT = f"""You are a PostgreSQL expert. Given a natural language question,
generate a single valid SELECT query for the following schema.
Only return the raw SQL query — no explanation, no markdown, no code blocks.
Use only SELECT statements. Never use DROP, DELETE, INSERT, UPDATE, TRUNCATE, ALTER, CREATE.

SCHEMA:
{DB_SCHEMA}"""


def _generate_sql(question: str) -> str:
    llm = get_llm(max_tokens=512)
    messages = [
        SystemMessage(content=_SQL_SYSTEM_PROMPT),
        HumanMessage(content=question),
    ]
    response = llm.invoke(messages)
    sql = response.content.strip()
    # Strip markdown code block if LLM wraps it
    if sql.startswith("```"):
        lines = sql.split("\n")
        sql = "\n".join(lines[1:-1]) if len(lines) > 2 else sql
    return sql.strip()


# Shared metadata collector — populated during tool execution and read by the agent
_tool_metadata: dict[str, Any] = {
    "sql_queries": [],
    "tables_accessed": [],
}


def reset_tool_metadata():
    _tool_metadata["sql_queries"] = []
    _tool_metadata["tables_accessed"] = []


def get_tool_metadata() -> dict:
    return _tool_metadata


@tool
def query_customer_database(question: str) -> str:
    """Use this tool when you need to find customer audiences, flight history,
    demographics, or any structured customer data."""
    request_id = "unknown"
    generated_sql = ""
    start = time.time()

    try:
        generated_sql = _generate_sql(question)
        logger.info(json.dumps({"event": "sql_generated", "sql": generated_sql}))

        # Validate through all 3 security layers
        valid, reason = validate_sql(generated_sql)
        elapsed = int((time.time() - start) * 1000)
        if not valid:
            log_query_event(
                event_type="sql_query",
                status="rejected",
                sql=generated_sql,
                tables=[],
                exec_time_ms=elapsed,
                rows=0,
                request_id=request_id,
                rejection_layer="sql_validation",
                rejection_reason=reason,
            )
            return f"Query rejected by security validation: {reason}"

        # Execute using read-only user
        conn = get_connection("readonly")
        try:
            rows = execute_query(conn, generated_sql)
        except psycopg2.extensions.QueryCanceledError:
            elapsed = int((time.time() - start) * 1000)
            log_query_event(
                event_type="sql_query",
                status="rejected",
                sql=generated_sql,
                tables=[],
                exec_time_ms=elapsed,
                rows=0,
                request_id=request_id,
                rejection_layer="timeout",
                rejection_reason="Query timed out after 5 seconds",
            )
            return "Query timed out after 5 seconds"
        finally:
            conn.close()

        elapsed = int((time.time() - start) * 1000)

        # Track metadata
        _tool_metadata["sql_queries"].append(generated_sql)

        # Log with masking (Layer 5)
        masked_rows = [mask_row(row) for row in rows]
        log_query_event(
            event_type="sql_query",
            status="allowed",
            sql=generated_sql,
            tables=[],
            exec_time_ms=elapsed,
            rows=len(rows),
            request_id=request_id,
        )
        logger.info(json.dumps({
            "event": "sql_results",
            "row_count": len(rows),
            "sample": masked_rows[:2],
        }))

        if not rows:
            return "No data found for this query."

        return json.dumps(rows, default=str)

    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        logger.error(json.dumps({"event": "sql_tool_error", "error": str(exc)}))
        return f"Error executing query: {exc}"
