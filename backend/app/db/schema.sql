PRAGMA journal_mode = WAL;

PRAGMA foreign_keys = ON;

CREATE TABLE
    IF NOT EXISTS users (
        id TEXT PRIMARY KEY, -- Firebase UID
        email TEXT,
        name TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime ('now'))
    );

CREATE TABLE
    IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime ('now'))
    );

CREATE TABLE
    IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL, -- Yahan text ya image ka local reference hoga
        created_at TEXT NOT NULL DEFAULT (datetime ('now'))
    );