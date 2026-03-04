import json
import os
from typing import Literal

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Module-level cache so Lambda doesn't call Secrets Manager on every invocation
_secret_cache: dict[str, str] = {}


def _get_secret(secret_name: str) -> str:
    if secret_name in _secret_cache:
        return _secret_cache[secret_name]
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    secret = response["SecretString"]
    try:
        parsed = json.loads(secret)
        # Support both {"password": "..."} and plain string secrets
        password = parsed.get("password", secret)
    except (json.JSONDecodeError, AttributeError):
        password = secret
    _secret_cache[secret_name] = password
    return password


def get_connection(user_role: Literal["readonly", "app"]) -> psycopg2.extensions.connection:
    """
    Return a psycopg2 connection for the given role.
    - 'readonly'  → marketing_ai_readonly (used by LangChain Agent SQL tool)
    - 'app'       → marketing_ai_app      (used by application code for writes)
    """
    if user_role == "readonly":
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
    with conn.cursor() as cursor:
        cursor.execute("SET statement_timeout = '5000';")
        cursor.execute(sql)
        if cursor.description is not None:
            return [dict(row) for row in cursor.fetchall()]
        return []
