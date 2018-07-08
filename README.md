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

## Usage
```python
import asyncio
import uvloop
import aiowebsockets


class ClientProtocol(aiowebsockets.WebSocketProtocol):

  def connection_established(self):
    pass

  async def on_message(self, message, type):
    self.send(message)


if __name__ == '__main__':
  asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

  server = asyncio.get_event_loop().create_server(
    ClientProtocol, '0.0.0.0', 2053)

  asyncio.get_event_loop().run_until_complete(server)
  asyncio.get_event_loop().run_forever()

```
