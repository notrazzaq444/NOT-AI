"""SQLite connection factory + schema bootstrap."""
from __future__ import annotations

import sqlite3
import shutil
from contextlib import contextmanager
from pathlib import Path

from app.config.settings import get_settings


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _get_safe_db_path() -> Path:
    # Force db path to a guaranteed clean file in the backend folder
    base_dir = Path(__file__).resolve().parents[2]
    db_path = base_dir / "not.db"
    if db_path.is_dir():
        shutil.rmtree(db_path)
    return db_path


def _connect(db_path: Path = None) -> sqlite3.Connection:
    path = _get_safe_db_path()
    
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    path = _get_safe_db_path()
    if path.exists() and not path.is_file():
        path.unlink(missing_ok=True)
        
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.executescript(schema)
        conn.commit()


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connection():
    """Legacy alias for get_db."""
    return get_db()