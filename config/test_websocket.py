
import asyncio
import websockets


async def test():
    uri = "ws://127.0.0.1:8000/ws/interviews/101/"

    async with websockets.connect(uri) as ws:
        print("WebSocket connected!")

        await ws.send(
            '{"type": "test", "message": "Hello INTERVUE"}'
        )

        print("Message sent successfully")


asyncio.run(test())
