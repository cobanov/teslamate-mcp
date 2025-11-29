"""SQL query validation utilities"""

import re


def validate_sql_query(sql: str) -> tuple[bool, str | None]:
    """Validate SQL query to ensure it's read-only"""
    # Remove comments and strings
    sql_clean = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    sql_clean = re.sub(r"/\*.*?\*/", "", sql_clean, flags=re.DOTALL)
    sql_clean = re.sub(r"'[^']*'", "''", sql_clean)
    sql_clean = re.sub(r'"[^"]*"', '""', sql_clean)

    # Check for forbidden operations
    if re.search(
        r"\b(DROP|CREATE|INSERT|UPDATE|DELETE|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
        sql_clean,
        re.IGNORECASE,
    ):
        return False, "Only SELECT queries are allowed"

    # Must start with SELECT
    if not re.search(r"^\s*SELECT\b", sql_clean.strip(), re.IGNORECASE):
        return False, "Only SELECT statements are allowed"

    # No multiple statements
    if ";" in sql_clean.rstrip(";"):
        return False, "Multiple SQL statements are not allowed"

    return True, None
