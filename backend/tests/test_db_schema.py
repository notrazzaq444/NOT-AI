from app.db.connection import init_db, get_connection

def test_database_tables_exist():
    init_db()
    with get_connection() as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sessions", "messages", "memories", "permissions"} <= names
