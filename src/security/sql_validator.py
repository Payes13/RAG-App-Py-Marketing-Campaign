"""
SQL security validation — Layers 1, 2, and 3.

Every LLM-generated SQL query must pass all three layers before execution.
"""
import re

import sqlparse
from sqlparse.sql import Identifier, IdentifierList, Where, Parenthesis
from sqlparse.tokens import Keyword, DML

ALLOWED_TABLES = [
    "customers",
    "flights",
    "preferences",
    "document_embeddings",
    "generated_campaigns",
    "csv_files",
]

BLOCKED_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"--",
    r"/\*",
    r"\bUNION\b",
    r"\bpg_sleep\b",
    r"\binformation_schema\b",
    r"\bpg_catalog\b",
    r"\bpg_tables\b",
    r"\bpg_user\b",
    r"\bcopy\b",
    r";\s*\w",
]

COMPLEXITY_LIMITS = {
    "max_joins": 3,
    "max_subqueries": 1,
    "max_where_conditions": 10,
}


def _extract_table_names(parsed) -> list[str]:
    """Recursively extract table names from a parsed SQL statement."""
    tables = []
    from_seen = False
    join_seen = False

    for token in parsed.tokens:
        if token.ttype is Keyword and token.normalized.upper() in ("FROM", "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL JOIN", "CROSS JOIN"):
            from_seen = True
            join_seen = True
        elif from_seen:
            if isinstance(token, Identifier):
                tables.append(token.get_real_name())
                from_seen = False
            elif isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    if isinstance(identifier, Identifier):
                        tables.append(identifier.get_real_name())
                from_seen = False
            elif token.ttype is Keyword:
                from_seen = False

        # Recurse into subqueries
        if isinstance(token, Parenthesis):
            sub = sqlparse.parse(str(token))[0]
            tables.extend(_extract_table_names(sub))

    return [t for t in tables if t is not None]


def _count_joins(sql: str) -> int:
    pattern = re.compile(r"\bJOIN\b", re.IGNORECASE)
    return len(pattern.findall(sql))


def _count_subqueries(sql: str) -> int:
    """Count nested SELECT statements (subqueries)."""
    pattern = re.compile(r"\(\s*SELECT\b", re.IGNORECASE)
    return len(pattern.findall(sql))


def _count_where_conditions(sql: str) -> int:
    """Count AND/OR operators in WHERE clause as a proxy for condition count."""
    # Strip everything before WHERE
    where_match = re.search(r"\bWHERE\b(.*?)(?:\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)",
                             sql, re.IGNORECASE | re.DOTALL)
    if not where_match:
        return 0
    where_clause = where_match.group(1)
    and_or_count = len(re.findall(r"\b(AND|OR)\b", where_clause, re.IGNORECASE))
    return and_or_count + 1  # +1 for the first condition


def _layer1_table_whitelist(sql: str) -> tuple[bool, str]:
    """Layer 1: Reject if any table not in ALLOWED_TABLES is referenced."""
    parsed = sqlparse.parse(sql)
    if not parsed:
        return False, "Could not parse SQL"
    tables = _extract_table_names(parsed[0])
    for table in tables:
        if table.lower() not in ALLOWED_TABLES:
            return False, f"Table '{table}' is not allowed"
    return True, ""


def _layer2_blocked_patterns(sql: str) -> tuple[bool, str]:
    """Layer 2: Reject if any malicious pattern is detected."""
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            return False, f"Blocked pattern detected: '{pattern}'"
    return True, ""


def _layer3_complexity(sql: str) -> tuple[bool, str]:
    """Layer 3: Reject queries exceeding complexity thresholds."""
    joins = _count_joins(sql)
    if joins > COMPLEXITY_LIMITS["max_joins"]:
        return False, f"Query too complex: exceeded max_joins ({joins} > {COMPLEXITY_LIMITS['max_joins']})"

    subqueries = _count_subqueries(sql)
    if subqueries > COMPLEXITY_LIMITS["max_subqueries"]:
        return False, f"Query too complex: exceeded max_subqueries ({subqueries} > {COMPLEXITY_LIMITS['max_subqueries']})"

    conditions = _count_where_conditions(sql)
    if conditions > COMPLEXITY_LIMITS["max_where_conditions"]:
        return False, f"Query too complex: exceeded max_where_conditions ({conditions} > {COMPLEXITY_LIMITS['max_where_conditions']})"

    return True, ""


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    Run all three SQL security layers in order.
    Returns (True, "") if the query passes all layers.
    Returns (False, reason) on the first failed layer.
    """
    ok, reason = _layer1_table_whitelist(sql)
    if not ok:
        return False, reason

    ok, reason = _layer2_blocked_patterns(sql)
    if not ok:
        return False, reason

    ok, reason = _layer3_complexity(sql)
    if not ok:
        return False, reason

    return True, ""
