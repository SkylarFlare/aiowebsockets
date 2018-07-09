import asyncio
import uvloop
import time

import aiowebsockets


class Client(aiowebsockets.WebSocketProtocol):
    request_count = 0
    bytes_per_sec = 0

    def websocket_open(self):
        pass

    async def on_message(self, message, type):
        self.send(message, type)
        Client.bytes_per_sec += len(message)
        Client.request_count += 1


async def counter():
    last_iteration = time.time() * 1000

    while True:
        print(Client.bytes_per_sec, Client.request_count, time.time() * 1000 - last_iteration)
        last_iteration = time.time() * 1000
        Client.request_count = 0
        Client.bytes_per_sec = 0
        await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()

    server = loop.create_server(Client, '0.0.0.0', 2053)

    loop.run_until_complete(server)
    asyncio.ensure_future(counter())
    loop.run_forever()
