"""Database operations and connection management"""

import json
from pathlib import Path
from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import Config


class DatabaseManager:
    """Manages database connections and query execution"""

    def __init__(self, config: Config):
        self.connection_string = config.database_url
        self.queries_dir = Path(config.queries_dir)

    def read_sql_file(self, file_path: str) -> str:
        """Read SQL query from file"""
        full_path = self.queries_dir / file_path
        with open(full_path, "r") as file:
            return file.read()

    def execute_query_sync(self, sql_file_path: str) -> List[Dict[str, Any]]:
        """Execute SQL query synchronously"""
        sql_query = self.read_sql_file(sql_file_path)
        with psycopg.connect(self.connection_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_query)
                return cur.fetchall()

    async def execute_query_async(
        self, sql_file_path: str, pool: AsyncConnectionPool
    ) -> List[Dict[str, Any]]:
        """Execute SQL query asynchronously"""
        sql_query = self.read_sql_file(sql_file_path)
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql_query)
                return await cur.fetchall()

    async def execute_custom_query_async(
        self, query: str, pool: AsyncConnectionPool
    ) -> List[Dict[str, Any]]:
        """Execute a custom SQL query asynchronously"""
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query)
                return await cur.fetchall()

    @staticmethod
    def load_db_schema(
        schema_file: str = "data/all_db_info.json",
    ) -> List[Dict[str, str]]:
        """Load database schema from JSON file"""
        with open(schema_file, "r") as f:
            return json.load(f)


def create_async_pool(connection_string: str) -> AsyncConnectionPool:
    """Create an async connection pool"""
    return AsyncConnectionPool(
        connection_string, min_size=1, max_size=10, kwargs={"row_factory": dict_row}
    )
