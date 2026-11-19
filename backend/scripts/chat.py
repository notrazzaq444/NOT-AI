"""NOT CLI chat client."""
from __future__ import annotations

import asyncio
import json
import sys

import httpx
import websockets


BASE = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000"


async def main() -> None:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{BASE}/api/session")
            r.raise_for_status()
            session_id = r.json()["session_id"]
        except Exception as e:
            print(f"[chat] Cannot reach server at {BASE}: {e}")
            print("[chat] Start the server first:")
            print("       uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
            sys.exit(1)

    print(f"[chat] Session: {session_id}")
    print("[chat] Type your message. 'quit' or 'exit' to leave.\n")

    async with websockets.connect(f"{WS}/ws/{session_id}") as ws:
        while True:
            try:
                text = input("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[chat] bye")
                break
            if not text:
                continue
            if text.lower() in ("quit", "exit"):
                break

            await ws.send(json.dumps({"text": text}))
            print("NOT > ", end="", flush=True)

            try:
                while True:
                    raw = await ws.recv()
                    event = json.loads(raw)
                    etype = event["type"]

                    if etype == "token":
                        print(event["text"], end="", flush=True)
                    elif etype == "tool_call":
                        print(f"\n  [tool] {event['name']}({event['args']})", flush=True)
                    elif etype == "tool_result":
                        preview = event["result"].replace("\n", " ")[:120]
                        print(f"  [result] {preview}", flush=True)
                    elif etype == "error":
                        print(f"\n[error] {event['message']}")
                        break
                    elif etype == "end":
                        print("\n")
                        break
            except Exception as e:
                print(f"\n[chat] stream error: {e}")
                break


if __name__ == "__main__":
    asyncio.run(main())
