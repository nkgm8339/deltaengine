"""Direct stream endpoint probe."""
import asyncio
import json
import sys
import websockets


async def probe_direct(stream: str, n: int = 10) -> None:
    url = "wss://fstream.binance.com/ws/" + stream
    print(f"Connecting to {url}")
    async with websockets.connect(url) as ws:
        print("Connected")
        count = 0
        while count < n:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                print("Timeout - no message in 5s")
                break
            msg = json.loads(raw)
            e = msg.get("e", "?")
            print(f"msg {count}: e={e} keys={list(msg.keys())[:6]}")
            count += 1
    print(f"Total: {count}")


async def probe_subscribe(stream: str, n: int = 10) -> None:
    url = "wss://fstream.binance.com/ws"
    print(f"Connecting to {url} then SUBSCRIBE {stream}")
    async with websockets.connect(url) as ws:
        sub = json.dumps({"method": "SUBSCRIBE", "params": [stream], "id": 1})
        await ws.send(sub)
        count = 0
        while count < n:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                print("Timeout - no message in 5s")
                break
            msg = json.loads(raw)
            if "data" in msg:
                inner = msg["data"]
                e = inner.get("e", "?")
                print(f"WRAPPED msg {count}: stream={msg.get('stream')} e={e}")
            else:
                e = msg.get("e", "?")
                print(f"RAW msg {count}: e={e} keys={list(msg.keys())[:6]}")
            count += 1
    print(f"Total: {count}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "direct"
    stream = sys.argv[2] if len(sys.argv) > 2 else "btcusdt@trade"
    if mode == "direct":
        asyncio.run(probe_direct(stream))
    else:
        asyncio.run(probe_subscribe(stream))
