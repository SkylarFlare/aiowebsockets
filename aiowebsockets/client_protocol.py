import asyncio
import base64
import urllib.parse
import random
import ssl
import struct

from .protocol import Protocol
from .constants import Flags


class ClientProtocol(Protocol):

    def __init__(self, uri=None, *args, **kargs):
        """
        We need to setup a couple of async
        instances to wait for connection events
        and data, in order to pass it to our
        coroutine
        """
        super().__init__(*args, **kargs)
        self.uri = uri
        self.connection_event = asyncio.Event()
        self.recv_queue = asyncio.Queue()

    def connection_made(self, context):
        """
        Enable protocol masking websocket frames
        and send our HTTP header.
        Also calls Protocol.connection_made.
        """
        super().connection_made(context)
        self.flags |= Flags.MASK_DATA
        self.construct_and_send_header()

    def construct_and_send_header(self):
        """
        The connection has been established, now we tell our
        websocket server that we're indeed a WebSocket
        client.
        """
        self.ws_key = base64.b64encode(
            bytes(random.getrandbits(8) for i in range(16)))

        headers = ''.join([
            'GET {} HTTP/1.1\r\n'.format(self.uri.path or '/'),
            'Host: {}\r\n'.format(self.uri.netloc, self.uri.port),
            'Upgrade: websocket\r\n',
            'Connection: Upgrade\r\n',
            'Sec-WebSocket-Key: {}\r\n'.format(self.ws_key.decode('utf-8')),
            'Sec-WebSocket-Version: 13\r\n\r\n'
        ]).encode('utf-8')

        self.context.write(headers)

    def shake_hands(self):
        """
        Handshake response from WebSocket server,
        validate and upgrade. There is one small
        bug here, if the client sends data
        immediately after the handshake and we
        receive it in one iteration, receive_data
        won't be called on that frame until the
        next iteration.
        """
        handshake_fin = self.recv_buffer.find(b'\r\n\r\n')

        if handshake_fin:
            if self.recv_buffer[:12] == b'HTTP/1.1 101':
                self.flags |= Flags.HANDSHAKE_COMPLETE

            del self.recv_buffer[:handshake_fin + 4]
            self.connection_event.set()

    async def on_message(self, message, type):
        """
        A Websocket message was received, forward it
        to our queue, which then forwards it to
        our coroutine.
        """
        await self.recv_queue.put(message)

    def connection_lost(self, exc):
        """
        The connection to our websocket has been lost,
        forward this to our data queue AND event
        """
        self.connection_event.set()
        print('fuck off')
        self.recv_queue.put_nowait(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        """
        This is our actual iterator,
        self.recv_queue contains None when the
        client is disconnected.
        """
        queue_item = await self.recv_queue.get()

        if not queue_item:
            raise StopAsyncIteration

        return queue_item


class Connect:

    def __init__(self, uri):
        self.uri = urllib.parse.urlparse(uri, allow_fragments=False)

        if self.uri.scheme not in ('ws', 'wss'):
            raise ValueError('Unsupported protocol [ws/wss]://domain')

        if not self.uri.netloc:
            raise ValueError('Bad network address')

        if not self.uri.port:
            raise ValueError('No port provided in WS uri')

        self.connect_websocket()

    def connect_websocket(self):
        def factory():
            return ClientProtocol(uri=self.uri)

        addr = self.uri.netloc[:self.uri.netloc.find(':')]

        self.create_connection = asyncio.get_event_loop().create_connection(
            factory,
            addr,
            self.uri.port,
            ssl=(ssl.SSLContext() if self.uri.scheme.lower() == 'wss' else None)
        )

    async def __aenter__(self):
        transport, context = await self.create_connection
        await context.connection_event.wait()

        if not context.flags & Flags.HANDSHAKE_COMPLETE:
            raise ConnectionRefusedError()

        return context

    async def __aexit__(self, exc_type, exc, tb):
        pass
