from autobahn.asyncio.websocket import WebSocketServerProtocol, \
    WebSocketServerFactory


class MyServerProtocol(WebSocketServerProtocol):
    count = 0
    mps = 0

    # def onConnect(self, request):
    #    print("Client connecting: {0}".format(request.peer))

    def onOpen(self):
        MyServerProtocol.count += 1
        # print("WebSocket connection open.")

    def onMessage(self, payload, isBinary):
        MyServerProtocol.mps += 1
        self.sendMessage(payload, isBinary)

    def onClose(self, wasClean, code, reason):
        MyServerProtocol.count -= 1
        print("WebSocket connection closed: {0}".format(reason))


async def printer():
    while True:
        print(MyServerProtocol.count, MyServerProtocol.mps)
        MyServerProtocol.mps = 0
        await asyncio.sleep(1)


if __name__ == '__main__':
    import asyncio
    import uvloop

    factory = WebSocketServerFactory(u"ws://127.0.0.1:2053")
    factory.protocol = MyServerProtocol

    loop = asyncio.get_event_loop()
    asyncio.ensure_future(printer())
    coro = loop.create_server(factory, '0.0.0.0', 2053)
    server = loop.run_until_complete(coro)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        loop.close()
