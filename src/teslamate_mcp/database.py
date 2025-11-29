"""Database operations and connection management"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import Config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and query execution"""

    def __init__(self, config: Config):
        self.config = config
        self.connection_string = config.database_url
        self.queries_dir = Path(config.queries_dir)

    def read_sql_file(self, file_path: str) -> str:
        """Read SQL query from file"""
        try:
            full_path = self.queries_dir / file_path
            with open(full_path, "r") as file:
                return file.read()
        except FileNotFoundError:
            logger.error(f"SQL file not found: {full_path}")
            raise
        except IOError as e:
            logger.error(f"Error reading SQL file {full_path}: {e}")
            raise

    def execute_query_sync(self, sql_file_path: str) -> List[Dict[str, Any]]:
        """Execute SQL query synchronously (for stdio transport)"""
        try:
            sql_query = self.read_sql_file(sql_file_path)
            with psycopg.connect(self.connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql_query)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Error executing {sql_file_path}: {e}")
            raise

    async def execute_query_async(
        self, sql_file_path: str, pool: AsyncConnectionPool
    ) -> List[Dict[str, Any]]:
        """Execute SQL query asynchronously (for HTTP transport)"""
        try:
            sql_query = self.read_sql_file(sql_file_path)
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql_query)
                    results = await cur.fetchall()
                    return results
        except Exception as e:
            logger.error(f"Error executing {sql_file_path}: {e}")
            raise

    async def execute_custom_query_async(
        self, query: str, pool: AsyncConnectionPool
    ) -> List[Dict[str, Any]]:
        """Execute a custom SQL query asynchronously"""
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query)
                    results = await cur.fetchall()
                    return results
        except psycopg.errors.SyntaxError as e:
            raise ValueError(f"SQL syntax error: {e}")
        except psycopg.errors.UndefinedTable as e:
            raise ValueError(f"Table not found: {e}")
        except psycopg.errors.UndefinedColumn as e:
            raise ValueError(f"Column not found: {e}")
        except Exception as e:
            logger.error(f"Error executing SQL query: {e}")
            raise ValueError(f"Database error: {str(e)}")

    @staticmethod
    def load_db_schema(schema_file: str = "data/all_db_info.json") -> List[Dict[str, str]]:
        """Load database schema from JSON file"""
        try:
            with open(schema_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Database schema file {schema_file} not found")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing database schema: {e}")
            return []


# Create async connection pool
def create_async_pool(connection_string: str) -> AsyncConnectionPool:
    """Create an async connection pool"""
    return AsyncConnectionPool(
        connection_string, min_size=1, max_size=10, kwargs={"row_factory": dict_row}
    )

