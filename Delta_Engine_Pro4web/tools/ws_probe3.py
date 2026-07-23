"""Show first message fields."""
import asyncio, json, sys
import websockets


async def probe(stream: str) -> None:
    url = "wss://fstream.binance.com/ws/" + stream
    async with websockets.connect(url) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        print(json.dumps(msg, indent=2))


if __name__ == "__main__":
    s = sys.argv[1] if len(sys.argv) > 1 else "btcusdt@trade"
    asyncio.run(probe(s))
