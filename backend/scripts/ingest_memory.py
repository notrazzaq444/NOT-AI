"""Import approved key/value memories from a UTF-8 JSON file."""
import json, sys
from app.memory.store import MemoryStore

if len(sys.argv) != 2:
    raise SystemExit("Usage: python scripts/ingest_memory.py approved_memories.json")
items = json.loads(open(sys.argv[1], encoding="utf-8").read())
store = MemoryStore()
for item in items:
    store.save_fact(item["key"], item["value"], approved=True)
print(f"Imported {len(items)} approved memories.")
