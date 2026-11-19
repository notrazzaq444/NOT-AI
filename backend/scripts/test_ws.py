"""Quick WS test - proves the backend WebSocket route works."""
import asyncio
import json
import httpx
import websockets


async def main():
    async with httpx.AsyncClient() as client:
        r = await client.post("http://127.0.0.1:8000/api/session")
        r.raise_for_status()
        sid = r.json()["session_id"]
        print("session:", sid)

    async with websockets.connect(f"ws://127.0.0.1:8000/ws/{sid}") as ws:
        print("WS connected")
        await ws.send(json.dumps({"text": "hello"}))
        count = 0
        async for msg in ws:
            event = json.loads(msg)
            print("event:", event.get("type"), str(event)[:100])
            count += 1
            if event.get("type") == "end":
                break
            if count >= 20:
                print("(stopping after 20 events)")
                break


if __name__ == "__main__":
    asyncio.run(main())
