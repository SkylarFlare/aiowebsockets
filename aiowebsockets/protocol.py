import asyncio
import socket
import codecs
import struct
import urllib.parse

from .constants import Flags, STATUS_CODES, VALID_STATUS_CODES, OPCODES
from .constants import MAX_BUFFER_LENGTH
from .handshake import Handshake
from .exception import IncompleteFrame
from .exception import CloseFrame
from .exception import ProtocolError
from .exception import BufferExceeded
from .framing import Frame
from .framing import EncodeFrame


class Protocol(asyncio.Protocol):

    def set_nodelay(self):
        """
        Disable Nagle's Algorithm in order to avoid and latency
        when sending data through a websocket or raw connection.
        """
        sock = self.context.get_extra_info('socket')
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)

    def create_buffers(self):
        self.recv_buffer = bytearray()
        self.frag_decoder = codecs.getincrementaldecoder('utf-8')()
        self.frag_buffer = bytearray()
        self.frag_opcode = None
        self.flags = Flags.AWAITING_HANDSHAKE

    def connection_made(self, context):
        """
        Connection established called by asyncio's create_server
        class. We'll use this as an __init__ function and setup
        our various buffers. First up, let's handle our sockets.
        """
        self.context = context
        self.set_nodelay()
        self.create_buffers()

        self.opcode_handlers = {
            OPCODES['stream']: self.handle_stream_frame,
            OPCODES['text']: self.handle_binary_frame,
            OPCODES['binary']: self.handle_binary_frame,
            OPCODES['close']: self.handle_close_frame,
            OPCODES['ping']: self.handle_ping_frame,
            OPCODES['pong']: lambda x: None
        }

    def data_received(self, data):
        """
        Respond to WebSocket handshake requests and then iterate
        over websocket frames.
        """
        if self.flags & Flags.HANDSHAKE_COMPLETE:
            try:
                if len(data) + len(self.recv_buffer) > MAX_BUFFER_LENGTH:
                    raise BufferExceeded

                self.recv_buffer.extend(data)

                for frame in iter(self.frame_decoder, None):
                    del self.recv_buffer[:len(frame)]

                    if frame.opcode not in self.opcode_handlers:
                        raise ProtocolError('Unknown Opcode')

                    self.opcode_handlers[frame.opcode](frame)

            except IncompleteFrame:
                pass

            except ProtocolError:
                self.close_websocket(STATUS_CODES['protocol-error'])

            except UnicodeDecodeError:
                self.close_websocket(
                    STATUS_CODES['inconsistent-type'], "Invalid UTF-8 Data")

            except BufferExceeded:
                self.close_websocket(
                    STATUS_CODES['buffer-exceeded'], "Buffer Exceeded")

            except CloseFrame as frame:
                self.close_websocket(frame.status, frame.reason)

        else:
            self.recv_buffer.extend(data)
            self.shake_hands()

    def frame_decoder(self):
        """
        Just a wrapper so I can use iter() on data_received
        """
        return Frame(self.recv_buffer) if self.recv_buffer else None

    def handle_binary_frame(self, frame):
        '''
        We don't actually want to convert it to
        an str instance, just want to check that
        it's valid utf-8.
        '''
        if not frame.fin:
            self.handle_fragment_begin(frame)

        elif self.flags & Flags.FRAGMENTATION_STARTED:
            raise ProtocolError('Expected fragment/chunk with opcode 0')

        else:
            if frame.opcode == OPCODES['text']:
                """
                We decode to verify that it's valid utf8 here, but because
                we treat everything as a bytearray, we don't want the
                resulting bytes object.
                """
                frame.byte_data.decode('utf-8')

            asyncio.ensure_future(
                self.on_message(frame.byte_data, frame.opcode)
            )

    def handle_ping_frame(self, frame):
        if not frame.fin:
            raise ProtocolError('Control frames must not be fragmented')

        self.context.write(
            EncodeFrame(True, OPCODES['pong'], frame.byte_data)
        )

    def handle_close_frame(self, frame):
        """
        Handles a close frame sent by a WebSocket client
        """
        status, reason, length = (
            STATUS_CODES['close'], b'', len(frame.byte_data))

        if length >= 2:
            status = struct.unpack_from('!H', frame.byte_data[:2])[0]
            if status not in VALID_STATUS_CODES:
                status = STATUS_CODES['protocol-error']

            reason = frame.byte_data[2:]
            reason.decode('utf-8')

        elif length == 1:
            status = STATUS_CODES['protocol-error']

        raise CloseFrame(status, reason)

    def handle_fragment_begin(self, frame):
        """
        A fragment-beginning frame is text/binary with FIN=0
        """
        if frame.opcode in OPCODES['control']:
            raise ProtocolError('Control messages cannot be fragmented')

        # reset our flags and buffer
        self.frag_decoder.reset()
        self.flags |= Flags.FRAGMENTATION_STARTED
        self.frag_opcode = frame.opcode

        # Attempt to decode(verify) it, if it's a text frame
        if frame.opcode == OPCODES['text']:
            self.frag_decoder.decode(
                frame.byte_data, final=False)

        # Max Buffer length
        if len(frame.byte_data) > MAX_BUFFER_LENGTH:
            raise BufferExceeded()

        # Append fragment to the buffer
        self.frag_buffer.extend(frame.byte_data)

    def handle_stream_frame(self, frame):
        """
        Handle a stream of fragmented messages
        """
        if not self.flags & Flags.FRAGMENTATION_STARTED:
            raise ProtocolError('Received continuation before fin=0')

        # Decode if it's text frame, to make sure valid utf-8
        if self.frag_opcode == OPCODES['text']:
            self.frag_decoder.decode(frame.byte_data, final=frame.fin)

        # Verify buffer Length
        if len(frame.byte_data) + len(self.frag_buffer) > MAX_BUFFER_LENGTH:
            raise BufferExceeded

        # Extend the buffer
        self.frag_buffer.extend(frame.byte_data)

        # If last chunk, callback
        if frame.fin:
            self.flags &= ~Flags.FRAGMENTATION_STARTED
            buffer = self.frag_buffer.copy()
            self.frag_buffer.clear()

            # Callback
            asyncio.ensure_future(
                self.on_message(buffer, self.frag_opcode))

    def send(self, data, opcode=OPCODES['text']):
        """
        Send a text frame
        """
        if not isinstance(data, bytearray):
            if not isinstance(data, bytes):
                raise TypeError(
                    'Invalid data type, expecting bytes or bytearray')

            data = bytearray(data)

        to_send = EncodeFrame(
            True, opcode, data, mask=self.flags & Flags.MASK_DATA)

        self.context.write(to_send)

    def close_websocket(self, status=1000, reason='', mask=False):
        frame = bytearray(struct.pack('!H', status))

        if isinstance(reason, str):
            frame.extend(reason.encode('utf-8'))

        else:
            frame.extend(reason)

        self.context.write(EncodeFrame(True, OPCODES['close'], frame, mask))
        self.context.close()
        self.recv_buffer.clear()


class WebSocketProtocol(Protocol):

    def websocket_open(self):
        raise NotImplementedError('websocket_open not implemeneted')

    async def on_message(self, message, type=None):
        """
        Server acts as an echo server by default
        """
        self.context.write(EncodeFrame(True, type, message))

    def shake_hands(self):
        """
        Perform our WebSocket handshake and disconnect anything
        that doesn't look like one :')
        """
        header_end = self.recv_buffer.find(b'\r\n\r\n') + 4

        if header_end > -1:
            try:
                header = self.recv_buffer[:header_end]
                del self.recv_buffer[:header_end]

                self.header = Handshake(header)
                self.context.write(self.header.response_header)
                self.flags |= Flags.HANDSHAKE_COMPLETE

                self.websocket_open()

            except ValueError:
                self.context.write(b'HTTP/1.1 500 Bad Request\r\n\r\n')
                self.context.close()
                self.recv_buffer.clear()


class WebSocketClientProtocol(Protocol):

    def __init__(self, *args, **kargs):
        super().__init__(*args, **kargs)
        self.connection_event = asyncio.Event()
        self.recv_queue = asyncio.Queue()

    def connection_made(self, context):
        super().connection_made(context)
        self.flags |= Flags.MASK_DATA
        self.send_http_upgrade_header()

    def websocket_open(self):
        self.connection_event.set()

    def websocket_failed_open(self):
        self.connection_event.set()

    def send_http_upgrade_header(self):
        self.context.write(
            b'GET /chat HTTP/1.1\r\n'
            + b'Host: invalidhost.com:2053\r\n'
            + b'Upgrade: websocket\r\n'
            + b'Connection: Upgrade\r\n'
            + b'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n'
            + b'Sec-WebSocket-Version: 13\r\n\r\n'
        )

    def shake_hands(self):
        if self.recv_buffer[:12] == b'HTTP/1.1 101':
            self.flags |= Flags.HANDSHAKE_COMPLETE
            del self.recv_buffer[
                :self.recv_buffer.find(b'\r\n\r\n') + 4]

            self.websocket_open()

        else:
            self.context.close()
            self.websocket_failed_open()

    def connection_lost(self, exc):
        asyncio.ensure_future(self.recv_queue.put(None))

    async def on_message(self, message, type):
        await self.recv_queue.put(message)

    async def __aiter__(self):
        return self

    async def __anext__(self):
        queue_item = await self.recv_queue.get()

        if not queue_item:
            raise StopAsyncIteration

        return queue_item


class Connect:

    def __init__(self, uri):
        uri_context = urllib.parse.urlparse(uri)

        if not (uri_context.netloc and uri_context.scheme in ['ws', 'wss']):
            raise TypeError("Malformed WebSocket URI")

        name = uri_context.netloc
        if uri_context.port:
            name = name[:name.find(':')]

        self.create_connection = asyncio.get_event_loop().create_connection(
            WebSocketClientProtocol,
            name,
            uri_context.port or 80
        )

    async def __aenter__(self):
        transport, context = await self.create_connection
        await context.connection_event.wait()

        if not context.flags & Flags.HANDSHAKE_COMPLETE:
            raise ConnectionRefusedError

        return context

    async def __aexit__(self, exc_type, exc, tb):
        print('exiting context')
