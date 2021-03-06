import asyncio
import uvloop

import aiowebsockets


async def connect_client():
    async with aiowebsockets.Connect('ws://localhost:2053') as context:
        context.send(b'{"The":"Quick","Brown":"Fox","Jumped":"Over","The":"Lazy","Dog":"."}')

        async for message in context:
            context.send(message)


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    tasks = [connect_client() for i in range(1024)]

    asyncio.get_event_loop().run_until_complete(
        asyncio.wait(tasks))
