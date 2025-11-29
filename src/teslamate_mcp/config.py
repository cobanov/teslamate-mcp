"""Configuration management for TeslaMate MCP"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@dataclass
class Config:
    """Application configuration"""

    database_url: str
    auth_token: Optional[str] = None
    log_level: str = "INFO"
    queries_dir: str = "queries"

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")

        return cls(
            database_url=database_url,
            auth_token=os.getenv("AUTH_TOKEN"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            queries_dir=os.getenv("QUERIES_DIR", "queries"),
        )

    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger with the configured log level"""
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, self.log_level.upper()))
        return logger

