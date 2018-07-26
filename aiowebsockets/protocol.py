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
from .framing import FrameDecoder
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
        self.frame_decoder = FrameDecoder(self.recv_buffer)

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

                for frame in self.frame_decoder:
                    if frame.opcode not in self.opcode_handlers:
                        raise ProtocolError('Unknown Opcode')

                    if frame.rsv:
                        raise ProtocolError('RSV Bit Must Not Be Set')

                    self.opcode_handlers[frame.opcode](frame)
                    del self.recv_buffer[:len(frame)]

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

            except KeyboardInterrupt:
                asyncio.get_event_loop().stop()

        else:
            self.recv_buffer.extend(data)
            self.shake_hands()

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
                frame.data.decode('utf-8')

            if asyncio.iscoroutinefunction(self.on_message):
                asyncio.ensure_future(
                    self.on_message(frame.data, frame.opcode)
                )

            else:
                self.on_message(frame.data, frame.opcode)

    def handle_ping_frame(self, frame):
        if not frame.fin:
            raise ProtocolError('Control frames must not be fragmented')

        self.context.write(
            EncodeFrame(frame.data, 1, OPCODES['pong'])
        )

    def handle_close_frame(self, frame):
        """
        Handles a close frame sent by a WebSocket client
        """
        status, reason, length = (
            STATUS_CODES['close'], b'', len(frame.data))

        if length >= 2:
            status = struct.unpack_from('!H', frame.data[:2])[0]
            if status not in VALID_STATUS_CODES:
                status = STATUS_CODES['protocol-error']

            reason = frame.data[2:]
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
                frame.data, final=False)

        # Max Buffer length
        if len(frame.data) > MAX_BUFFER_LENGTH:
            raise BufferExceeded()

        # Append fragment to the buffer
        self.frag_buffer.extend(frame.data)

    def handle_stream_frame(self, frame):
        """
        Handle a stream of fragmented messages
        """
        if not self.flags & Flags.FRAGMENTATION_STARTED:
            raise ProtocolError('Received continuation before fin=0')

        # Decode if it's text frame, to make sure valid utf-8
        if self.frag_opcode == OPCODES['text']:
            self.frag_decoder.decode(frame.data, final=frame.fin)

        # Verify buffer Length
        if len(frame.data) + len(self.frag_buffer) > MAX_BUFFER_LENGTH:
            raise BufferExceeded

        # Extend the buffer
        self.frag_buffer.extend(frame.data)

        # If last chunk, callback
        if frame.fin:
            self.flags &= ~Flags.FRAGMENTATION_STARTED
            buffer = self.frag_buffer.copy()
            self.frag_buffer.clear()

            # Callback
            if asyncio.iscoroutinefunction(self.on_message):
                asyncio.ensure_future(
                    self.on_message(buffer, self.frag_opcode)
                )

            else:
                self.on_message(buffer, self.frag_opcode)

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
            data, 1, opcode, mask=self.flags & Flags.MASK_DATA)

        self.context.write(to_send)

    def close_websocket(self, status=1000, reason=''):
        frame = bytearray(struct.pack('!H', status))

        if isinstance(reason, str):
            frame.extend(reason.encode('utf-8'))

        else:
            frame.extend(reason)

        self.context.write(EncodeFrame(frame, 1, OPCODES['close']))
        self.context.close()
        self.recv_buffer.clear()


class WebSocketProtocol(Protocol):

    def websocket_open(self):
        raise NotImplementedError('websocket_open not implemeneted')

    async def on_message(self, message, type=None):
        """
        Server acts as an echo server by default
        """
        self.context.write(EncodeFrame(message, 1, type))

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
