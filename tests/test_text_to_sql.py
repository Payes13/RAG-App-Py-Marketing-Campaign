"""
Tests for SQL security validation layers 1, 2, and 3.
"""
import pytest

from src.security.sql_validator import validate_sql


class TestLayer1TableWhitelist:
    def test_allowed_tables_pass(self):
        sql = "SELECT * FROM customers WHERE age > 30"
        ok, reason = validate_sql(sql)
        assert ok, reason

    def test_allowed_multi_table_pass(self):
        sql = "SELECT c.name, f.route FROM customers c JOIN flights f ON c.id = f.customer_id"
        ok, reason = validate_sql(sql)
        assert ok, reason

    def test_disallowed_table_rejected(self):
        sql = "SELECT * FROM pg_catalog.pg_tables"
        ok, reason = validate_sql(sql)
        assert not ok
        assert "not allowed" in reason.lower() or "blocked" in reason.lower()

    def test_system_table_rejected(self):
        sql = "SELECT * FROM admin_users"
        ok, reason = validate_sql(sql)
        assert not ok


class TestLayer2BlockedPatterns:
    @pytest.mark.parametrize("sql", [
        "DROP TABLE customers",
        "DELETE FROM customers",
        "INSERT INTO customers VALUES (1)",
        "UPDATE customers SET name = 'x'",
        "TRUNCATE customers",
        "SELECT * FROM customers -- comment injection",
        "SELECT * FROM customers UNION SELECT * FROM flights",
        "SELECT pg_sleep(5)",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM customers; DROP TABLE customers",
    ])
    def test_blocked_patterns_rejected(self, sql):
        ok, reason = validate_sql(sql)
        assert not ok, f"Expected rejection for: {sql}"

    def test_clean_select_passes(self):
        sql = "SELECT name, city, age FROM customers WHERE country = 'Canada'"
        ok, reason = validate_sql(sql)
        assert ok, reason


class TestLayer3Complexity:
    def test_too_many_joins_rejected(self):
        sql = """
        SELECT c.name FROM customers c
        JOIN flights f ON c.id = f.customer_id
        JOIN preferences p ON c.id = p.customer_id
        JOIN generated_campaigns gc ON gc.route = f.route
        JOIN csv_files cf ON cf.id = 1
        """
        ok, reason = validate_sql(sql)
        assert not ok
        assert "join" in reason.lower()

    def test_max_joins_allowed(self):
        sql = """
        SELECT c.name, f.route, p.seat_type
        FROM customers c
        JOIN flights f ON c.id = f.customer_id
        JOIN preferences p ON c.id = p.customer_id
        """
        ok, reason = validate_sql(sql)
        assert ok, reason

    def test_subquery_within_limit(self):
        sql = "SELECT * FROM customers WHERE id IN (SELECT customer_id FROM flights WHERE route = 'MTL-NYC')"
        ok, reason = validate_sql(sql)
        assert ok, reason
