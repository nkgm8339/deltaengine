"""WS probe — subscribe to one stream and print first N messages."""
import asyncio
import json
import sys
import websockets


async def probe(stream: str, n: int = 20) -> None:
    url = "wss://fstream.binance.com/ws"
    async with websockets.connect(url) as ws:
        sub = json.dumps({"method": "SUBSCRIBE", "params": [stream], "id": 1})
        await ws.send(sub)
        count = 0
        while count < n:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                print("timeout waiting for message")
                break
            msg = json.loads(raw)
            if "data" in msg:
                inner = msg["data"]
                e = inner.get("e", "?")
                print(f"WRAPPED stream={msg.get('stream')} e={e}")
            else:
                e = msg.get("e", "?")
                print(f"RAW e={e} keys={list(msg.keys())[:5]}")
            count += 1
    print(f"Total received: {count}")


if __name__ == "__main__":
    stream = sys.argv[1] if len(sys.argv) > 1 else "btcusdt@trade"
    asyncio.run(probe(stream))
