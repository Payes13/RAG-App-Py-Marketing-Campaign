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
"""
_tool_metadata is a module-level global dict — it lives at the top of the file, outside any function, so it persists for the lifetime of the Python process. In Lambda, this means it survives across warm invocations (when Lambda reuses the same container for a second request). Without resetting it, request 2 would see request 1's SQL queries mixed in.

That's exactly why reset_tool_metadata() exists and why it's called at the top of every run_marketing_agent()

_tool_metadata is defined at the top of the file, outside any function — that makes it module-level. Python runs that line once when the file is first imported, then never again.

Every function in that file can read and modify it, and it keeps its value between calls because nobody re-initializes it. That's why reset_tool_metadata() has to explicitly wipe it — otherwise the list just keeps growing across requests.

The underscore prefix _tool_metadata is a Python convention meaning "this is private to this module, don't import it from outside." It's not enforced by the language — it's just a signal to other developers.
"""
"""
Why metadata is stored inside query_customer_database?. The tool's job is to answer the agent's question and return a string. But the app also needs to produce a metadata PDF showing what happened during the request — which SQL queries ran, which tables were accessed. The tool itself is the only place that knows this. So every time the tool runs successfully, it records what it did:
# text_to_sql_tool.py:182
_tool_metadata["sql_queries"].append(generated_sql)
After the agent finishes, marketing_agent.py reads it:
# marketing_agent.py:189
sql_meta = get_tool_metadata()
metadata = {
    "sql_queries": sql_meta.get("sql_queries", []),   # goes into the metadata PDF
    ...
}
"""
_tool_metadata: dict[str, Any] = {
    "sql_queries": [],
    "tables_accessed": [],
}

def reset_tool_metadata():
    _tool_metadata["sql_queries"] = []
    _tool_metadata["tables_accessed"] = []

def get_tool_metadata() -> dict:
    return _tool_metadata

# A decorator wraps a function and adds behavior to it. @tool is LangChain's decorator that transforms a plain Python function into a LangChain Tool object — which has extra properties the agent needs:. After the decorator runs, query_customer_database is no longer a plain function — it's a Tool object with: .name → "query_customer_database" (from the function name), .description → "Use this tool when you need to find customer audiences..." (from the docstring), .func → the original function, stored inside. The agent reads .name and .description to decide which tool to pick for a given task. That docstring is literally what the LLM reads to understand what each tool does. the """""" is the docstring that will be used by the LLM.
"""
That docstring is the tool description the LLM reads at runtime to decide which tool to pick. It's not documentation for a human developer — it's an instruction to the AI.

When the ReAct agent runs, LangChain builds a prompt that lists all available tools like this:

query_customer_database: Use this tool when you need to find customer audiences, flight history, demographics, or any structured customer data.
"""

"""
The LLM never directly calls the function. Here's what actually happens:

Step 1 — The LLM outputs plain text

When the agent runs, the LLM produces a text string following the ReAct format defined in the prompt template:
Thought: I need customer demographics for the Montreal-San Salvador route.
Action: query_customer_database
Action Input: How many customers flew Montreal to San Salvador in the last 12 months and what are their demographics?

That's just text. The LLM doesn't "call" anything — it writes words.

Step 2 — AgentExecutor parses that text

AgentExecutor reads the LLM's output and looks for the Action: and Action Input: lines. It extracts:

tool name → "query_customer_database"
tool input → "How many customers flew Montreal to San Salvador..."

Step 3 — AgentExecutor makes the actual function call
# What AgentExecutor does internally — you never write this:
tool = tools_by_name["query_customer_database"]   # looks up the Tool object
result = tool.func("How many customers flew Montreal to San Salvador...")
#                   ↑ this is where `question` gets its value

Step 4 — Result fed back to the LLM

The tool's return value gets appended to the prompt as an Observation:, and the LLM reads it to decide what to do next.

So the full chain is:
LLM writes text → AgentExecutor parses it → AgentExecutor calls the function → 
function runs with question="..." → returns a string → AgentExecutor feeds it back to LLM
The programmer never passes question manually — AgentExecutor is the middleman that bridges the LLM's text output to real function calls.
"""
@tool
def query_customer_database(question: str) -> str:
    """Use this tool when you need to find customer audiences, flight history, demographics, or any structured customer data."""
    request_id = "unknown"
    generated_sql = ""
    # RETURNS SECONDS
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
        # USING with SYNTAX
        """
        try:
            with get_connection("readonly") as conn:
                rows = execute_query(conn, generated_sql)

        except psycopg2.extensions.QueryCanceledError:
            elapsed = int((time.time() - start) * 1000)
            ...

            return "Query timed out after 5 seconds"

        # When the with block finishes conn.close() IS EXECUTED AUTOMATICALLY
        """
        conn = get_connection("readonly")
        try:
            # rows looks like:
            # [
            #   {"id": 1, "name": "Alice"},
            #   {"id": 2, "name": "Bob"}
            # ]
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
