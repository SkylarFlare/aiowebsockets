import hashlib
import base64

from .constants import Flags


HANDSHAKE_MAGIC = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
HANDSHAKE_TEMPLATE = (
    b'HTTP/1.1 101 Switching Protocols',
    b'Upgrade: WebSocket',
    b'Connection: Upgrade',
    b'Sec-WebSocket-Accept: %s',
    b'\r\n'
)


class Handshake:

    def __init__(self, raw_data):
        """
        Let's just setup a few variables here
        """
        self.headers = {}

        self.parse_headers(raw_data)
        self.check_header()

    def parse_headers(self, raw_data):
        """
        Parse the header into a nice dictionary, in the future
        we could look at using http.server's BaseRequestHandler
        to parse it for us instead of using this ghetto method.
        """
        for header in raw_data.split(b'\r\n'):
            header_args = header.split(b': ', 1)

            if len(header_args) == 2:
                self.headers[
                    header_args[0].decode('utf-8')] = header_args[1]

    def check_header(self):
        """
        Make sure our client is trying to upgrade their connection,
        otherwise we don't really care about them.
        """
        if 'Sec-WebSocket-Key' not in self.headers:
            raise ValueError('Sec-WebSocket-Key not in headers')

        if 'Connection' not in self.headers:
            raise ValueError('Sec-WebSocket-Key not in headers')

        if 'Upgrade' not in self.headers:
            raise ValueError('Sec-WebSocket-Key not in headers')

    @property
    def response_header(self):
        ws_challenge = self.headers['Sec-WebSocket-Key'] + HANDSHAKE_MAGIC
        ws_challenge = hashlib.sha1(ws_challenge).digest()
        ws_challenge = base64.b64encode(ws_challenge)

        return b'\r\n'.join(HANDSHAKE_TEMPLATE) % ws_challenge
