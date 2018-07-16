<h1>aiowebsockets</h1>
AIOWebsockets is a callback based websocket protocol to extend asyncio's default protocol, it
is suggested that you use uvloop alongside aiowebsockets for maximum performance.
  
AIOWebsockets is RFC6455 compliant, tested using autobahn.


## Building/Installing
```python
pip install git+https://github.com/SkylarFlare/aiowebsockets.git  

# OR  

python setup.py build
python setup.py install
```

## Server Usage
```python
import asyncio
import uvloop
import aiowebsockets


class ClientProtocol(aiowebsockets.WebSocketProtocol):

  def websocket_open(self):
    pass

  """
  Using async keyword on on_message is also acceptable,
  though keep in mind that using async will incur a small
  performance hit.
  
  async def on_message(self):
    pass
  """

  def on_message(self, message, type):
    self.send(message)

  def connection_lost(self):
    # run any cleanup steps
    pass


if __name__ == '__main__':
  asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

  server = asyncio.get_event_loop().create_server(
    ClientProtocol, '0.0.0.0', 2053)

  asyncio.get_event_loop().run_until_complete(server)
  asyncio.get_event_loop().run_forever()

```

## Client Usage
```python
import asyncio
import uvloop

import aiowebsockets


async def connect_client():
  async with aiowebsockets.Connect('wss://localhost:2053') as context:
    context.send(b'One arbitrary message')
    context.send(b'Another arbitrary message')

    async for message in context:
      print(message)

    print("Disconnected")


if __name__ == '__main__':
  asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
  asyncio.get_event_loop().run_until_complete(connect_client())

```