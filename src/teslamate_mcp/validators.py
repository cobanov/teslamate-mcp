"""SQL query validation utilities"""

import re
from typing import Optional


def validate_sql_query(sql: str) -> tuple[bool, Optional[str]]:
    """
    Validate SQL query to ensure it's read-only.

    Args:
        sql: The SQL query to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Remove SQL comments
    # Remove single-line comments
    sql_no_comments = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    # Remove multi-line comments
    sql_no_comments = re.sub(r"/\*.*?\*/", "", sql_no_comments, flags=re.DOTALL)

    # Remove string literals to avoid false positives
    # This is a simplified approach - a full SQL parser would be more accurate
    sql_no_strings = re.sub(r"'[^']*'", "''", sql_no_comments)
    sql_no_strings = re.sub(r'"[^"]*"', '""', sql_no_strings)

    # Check for forbidden operations in the cleaned SQL
    forbidden_pattern = (
        r"\b(DROP|CREATE|INSERT|UPDATE|DELETE|ALTER|TRUNCATE|GRANT|REVOKE)\b"
    )
    if re.search(forbidden_pattern, sql_no_strings, re.IGNORECASE):
        return (
            False,
            "Forbidden SQL operation detected. Only SELECT queries are allowed.",
        )

    # Check for EXEC/EXECUTE
    if re.search(r"\b(EXEC|EXECUTE)\s*\(", sql_no_strings, re.IGNORECASE):
        return (
            False,
            "Forbidden SQL operation detected. Only SELECT queries are allowed.",
        )

    # Basic check for SELECT statement
    if not re.search(r"^\s*SELECT\b", sql_no_comments.strip(), re.IGNORECASE):
        return False, "Only SELECT statements are allowed."

    # Check for semicolons that might indicate multiple statements
    cleaned = sql_no_comments.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]  # Remove trailing semicolon

    if ";" in cleaned:
        return False, "Multiple SQL statements are not allowed."

    return True, None

