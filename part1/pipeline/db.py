import os
from pathlib import Path

import psycopg

DEFAULT_URL = "postgresql://localhost:5432/market_radar"
SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == "DATABASE_URL" and value.strip():
                return value.strip().strip("\"'")
    return DEFAULT_URL


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=False)


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA_FILE.read_text())
    conn.commit()
