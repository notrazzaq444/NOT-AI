"""Persistent Memory using ChromaDB (Vector Database)."""
import chromadb
from chromadb.config import Settings
from app.config.settings import get_settings

class MemoryStore:
    def __init__(self):
        settings = get_settings()
        # ChromaDB ka folder banayein agar nahi hai
        memory_path = settings.memory_dir / "chroma"
        memory_path.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=str(memory_path),
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection("conversations")
    
    def add_memory(self, text: str, metadata: dict, mem_id: str):
        try:
            self.collection.add(
                documents=[text],
                metadatas=[metadata],
                ids=[mem_id]
            )
            print(f"[Memory] Saved: {text[:50]}...")
        except Exception as e:
            print(f"[Memory] Save error: {e}")
    
    def search_memory(self, query: str, n_results: int = 3) -> list[str]:
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            if results["documents"] and results["documents"][0]:
                return results["documents"][0]
            return []
        except Exception as e:
            print(f"[Memory] Search error: {e}")
            return []