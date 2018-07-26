import asyncio
import uvloop

import aiowebsockets


async def connect_client():
    async with aiowebsockets.Connect('wss://echo.websocket.org:443') as context:
        context.send(b'One arbitrary message')
        context.send(b'Another arbitrary message')

        async for message in context:
            print(message)

        print("Disconnected")


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(connect_client())
