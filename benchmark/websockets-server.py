#!/usr/bin/env python
# from https://github.com/aaugustin/websockets

import asyncio
import uvloop
import websockets


class Count:
    counter = 0
    clients = 0


async def echo(websocket, path):
    try:
        Count.clients += 1

        async for message in websocket:
            await websocket.send(message)
            Count.counter += 1

    finally:
        Count.clients -= 1


async def countme():
    while True:
        print(Count.clients, Count.counter)
        Count.counter = 0
        await asyncio.sleep(1)

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
asyncio.get_event_loop().run_until_complete(
    websockets.serve(echo, 'localhost', 2053))
asyncio.ensure_future(countme())
asyncio.get_event_loop().run_forever()
