import asyncio
import socket
import codecs
import struct

from .constants import Flags
from .constants import STATUS_CODES
from .constants import VALID_STATUS_CODES
from .constants import OPCODES
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
        self.connection_established()

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
                    self.recv_buffer = self.recv_buffer[len(frame):]
                    self.handle_frame(frame)

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
        return Frame(self.recv_buffer)

    def handle_frame(self, frame):
        """
        Handle control frames and data frames
        """
        if frame.opcode == OPCODES['close']:
            self.handle_close_frame(frame)

        elif not frame.fin:
            self.handle_fragment_frame(frame)

        elif frame.opcode == OPCODES['stream']:
            self.handle_stream_frame(frame)

        elif frame.opcode == OPCODES['ping']:
            self.handle_ping_frame(frame)

        elif frame.opcode == OPCODES['pong']:
            pass

        elif self.flags & Flags.FRAGMENTATION_STARTED:
            raise ProtocolError('Received fragment extension before started')

        else:
            # Regular Message
            if frame.opcode == OPCODES['text']:
                frame.byte_data.decode('utf-8')

            asyncio.ensure_future(
                self.on_message(frame.byte_data, frame.opcode)
            )

    def handle_ping_frame(self, frame):
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

    def handle_fragment_frame(self, frame):
        """
        Handles a fragment frame that is not a stream
        """
        if frame.opcode != OPCODES['stream']:
            self.handle_fragment_begin(frame)

        elif not self.flags & Flags.FRAGMENTATION_STARTED:
            raise ProtocolError('Received fragment extention before start')

        else:
            self.handle_fragment_extension(frame)

    def handle_fragment_begin(self, frame):
        """
        Fragment block begin
        """
        if frame.opcode in OPCODES['control']:
            raise ProtocolError('Control messages cannot be fragmented')

        # reset our flags and buffer
        self.frag_decoder.reset()
        self.flags |= Flags.FRAGMENTATION_STARTED
        self.frag_opcode = frame.opcode

        # Attempt to decode it, if it's a text frame
        if frame.opcode == OPCODES['text']:
            self.frag_decoder.decode(
                frame.byte_data, final=False)

        # Max Buffer length
        if len(frame.byte_data) > MAX_BUFFER_LENGTH:
            raise BufferExceeded()

        # Append fragment to the buffer
        self.frag_buffer.clear()
        self.frag_buffer.extend(frame.byte_data)

    def handle_fragment_extension(self, frame):
        """
        Extends our fragment buffer
        """
        if self.frag_opcode == OPCODES['text']:
            self.frag_decoder.decode(
                frame.byte_data, final=False)

        # Max Buffer length
        if len(frame.byte_data) + len(self.frag_buffer) > MAX_BUFFER_LENGTH:
            raise BufferExceeded()

        self.frag_buffer.extend(frame.byte_data)

    def handle_stream_frame(self, frame):
        """
        Handle the end of a fragment stream
        """
        if not self.flags & Flags.FRAGMENTATION_STARTED:
            raise ProtocolError('Received continuation before start')

        # Decode if text frame
        if self.frag_opcode == OPCODES['text']:
            self.frag_decoder.decode(frame.byte_data, final=True)

        # Max Buffer length
        if len(frame.byte_data) + len(self.frag_buffer) > MAX_BUFFER_LENGTH:
            raise BufferExceeded()

        # Extend our buffer
        buffer = self.frag_buffer.copy()
        buffer.extend(frame.byte_data)

        self.frag_buffer.clear()
        self.flags &= ~Flags.FRAGMENTATION_STARTED

        # Call our async routine
        asyncio.ensure_future(
            self.on_message(buffer, self.frag_opcode)
        )

    def shake_hands(self):
        """
        Perform our WebSocket handshake and disconnect anything
        that doesn't look like one :')
        """
        header_end = self.recv_buffer.find(b'\r\n\r\n') + 4

        if header_end > -1:
            try:
                header = self.recv_buffer[:header_end]
                self.recv_buffer = self.recv_buffer[header_end:]

                result = Handshake(header)
                self.context.write(result.response_header)
                self.flags |= Flags.HANDSHAKE_COMPLETE

            except ValueError:
                self.context.write(b'HTTP/1.1 500 Bad Request\r\n\r\n')
                self.context.close()
                self.recv_buffer.clear()

    def send(self, data, opcode=OPCODES['text']):
        """
        Send a text frame
        """
        to_send = EncodeFrame(True, opcode, data)
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

    def connection_established(self):
        raise NotImplementedError('Connection established not implemeneted')

    async def on_message(self, message, type=None):
        self.context.write(EncodeFrame(True, type, message))