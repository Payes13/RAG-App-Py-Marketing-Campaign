import json
import os
from typing import Literal

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Module-level cache so Lambda doesn't call Secrets Manager on every invocation
_secret_cache: dict[str, str] = {}

def _get_secret(secret_name: str) -> str:
    # if secret_name in _secret_cache: return _secret_cache[secret_name]
    # Lambda can stay "warm" and handle multiple requests without restarting. Without the cache, every single request would call Secrets Manager — that's slow and costs money. The cache stores the secret in memory after the first fetch, so subsequent invocations on the same warm Lambda skip the API call entirely. The cache lives at module level (outside any function) so it persists across invocations.
    if secret_name in _secret_cache:
        return _secret_cache[secret_name]
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    secret = response["SecretString"]
    try:
        parsed = json.loads(secret)
        # Support both {"password": "..."} and plain string secrets
        """
        Why the fallback to secret?
        Because not all Secrets Manager secrets use the same key name. Someone might have stored it as:
        {"db_password": "abc"}   ← key is "db_password", not "password"
        {"apiKey": "abc"}        ← completely different key
        In those cases, parsed.get("password", ...) would find nothing and fall back. The fallback secret is the raw JSON string itself — not ideal, but it prevents a crash and lets the error surface naturally when the DB connection fails with a bad password.
        In TypeScript: parsed?.password ?? secret
        """
        password = parsed.get("password", secret)
    except (json.JSONDecodeError, AttributeError):
        password = secret
    _secret_cache[secret_name] = password
    return password

# Literal["readonly", "app"] on line 29
# Literal is a type hint that restricts the allowed values to an exact list — not just "any string", but only "readonly" or "app". If you pass anything else, your IDE will warn you before you even run the code.
# TS Equivalent: function getConnection(userRole: "readonly" | "app"): Connection { ... }
"""
psycopg2.extensions.connection return type
psycopg2 is Python's PostgreSQL driver (like pg or node-postgres in Node). psycopg2.extensions.connection is the type of the connection object it returns — the thing you use to send queries to the database. It's just for type-hinting purposes; it tells callers "this function hands you back a live DB connection."
"""
def get_connection(user_role: Literal["readonly", "app"]) -> psycopg2.extensions.connection:
    """
    Return a psycopg2 connection for the given role.
    - 'readonly'  → marketing_ai_readonly (used by LangChain Agent SQL tool)
    - 'app'       → marketing_ai_app      (used by application code for writes)
    """
    if user_role == "readonly":
        # The .get(key, default) form reads an env var but falls back to the second argument if it's not set.
        # Where do they come from? Two places:
        # Locally: your .env file (copied from .env.example)
        # In Lambda: the CDK stack sets them explicitly in common_env at marketing_ai_stack.py:118-119
        """
        That string: marketing_ai_readonly, on line 37 is just hardcoded — the code assumes the user already exists in PostgreSQL. It's created in scripts/init_db.sql, which you run once when setting up the database. 
        """
        secret_name = os.environ.get("DB_READONLY_SECRET_NAME", "marketing-ai/db-readonly-password")
        db_user = "marketing_ai_readonly"
    elif user_role == "app":
        secret_name = os.environ.get("DB_APP_SECRET_NAME", "marketing-ai/db-app-password")
        db_user = "marketing_ai_app"
    else:
        raise ValueError(f"Unknown user_role: {user_role!r}. Must be 'readonly' or 'app'.")

    password = _get_secret(secret_name)

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=db_user,
        password=password,
        cursor_factory=RealDictCursor,
    )
    return conn

def execute_query(conn: psycopg2.extensions.connection, sql: str) -> list[dict]:
    """
    Execute a SQL query with Layer 4 timeout enforcement (5 seconds).
    Returns results as a list of dicts.
    Raises psycopg2.extensions.QueryCanceledError on timeout.
    """

    """
    This is Python's context manager syntax — the with block.
    It does two things in one line:
    Opens/creates a resource (here: a DB cursor)
    Automatically cleans it up when the block ends, even if an error occurs
    A cursor is the object you use to actually send SQL to the database. Without it you can't run queries.
    The as cursor part just gives it a name so you can use it inside the block — same as:
    const cursor = conn.cursor();
    try {
    cursor.execute("...");
    // ...
    } finally {
    cursor.close(); // always runs, even if an error was thrown
    }
    The Python with block handles that finally { cursor.close() } for you automatically. You never have to call .close() yourself — the moment execution leaves the with block (normally or due to an exception), the cursor is closed and its resources are freed.
    You'll see this pattern everywhere in Python for anything that needs to be "opened and closed" — files, DB connections, locks, HTTP sessions, etc. It's the Python equivalent of TypeScript's try/finally cleanup pattern or Node's using keyword.
    """
    with conn.cursor() as cursor:
        cursor.execute("SET statement_timeout = '5000';")
        cursor.execute(sql)
        if cursor.description is not None:
            return [dict(row) for row in cursor.fetchall()]
        return []
