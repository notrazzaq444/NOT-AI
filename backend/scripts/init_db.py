"""Create data directories, SQLite DB, and seed default permissions."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings
from app.db.connection import get_db, init_db


DEFAULT_PERMISSIONS = [
    ("system.time", 1),
    ("system.calculate", 1),
    ("web.search", 1),
    ("web.open_url", 1),
    ("file.read", 1),
    ("file.create", 1),
    ("file.delete", 0),
    ("app.launch", 0),
    ("desktop.control", -1),
    ("terminal.execute", -1),
    ("software.install", -1),
]


def main() -> int:
    settings = get_settings()
    settings.ensure_directories()
    init_db()

    with get_db() as conn:
        conn.executemany(
            """
            INSERT INTO permissions (action, granted)
            VALUES (?, ?)
            ON CONFLICT(action) DO NOTHING
            """,
            DEFAULT_PERMISSIONS,
        )
        conn.commit()

    print(f"[NOT] Data dir : {settings.data_dir}")
    print(f"[NOT] DB       : {settings.db_path}")
    print(f"[NOT] Memory   : {settings.memory_dir}")
    print("[NOT] Database initialised with default permissions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())