import struct
import random

from .exception import IncompleteFrame, ProtocolError
from .constants import OPCODES


try:
    from .fast_mask import fast_mask

except ImportError:
    print('Could not import fast_mask.c; defaulting to utils.fast_mask')
    from .utils import fast_mask


cdef class FrameDecoder:
    cdef readonly int fin, opcode, masked, rsv, payload_len, payload_start
    cdef bytearray buffer
    cdef readonly bytearray data

    def __init__(self, buffer):
        self.buffer = buffer
        self.data = bytearray()
        self.fin = 0
        self.opcode = 0
        self.masked = 0
        self.rsv = 0
        self.payload_len = 0
        self.payload_start = 0

    cdef process_header(self):
        """
        Interpret the websocket headers
        """
        # Make sure we have the first two available bytes before anything else
        if len(self.buffer) < 2:
            raise StopIteration

        self.fin = self.buffer[0] & 0x80
        self.opcode = self.buffer[0] & 0x0f
        self.masked = self.buffer[1] & 0x80
        self.rsv = self.buffer[0] & 0x70

    cdef process_length(self):
        """
        Figure out the length of the frame
        """
        self.payload_len = self.buffer[1] & 0x7f
        self.payload_start = 2

        if self.payload_len == 126:
            if len(self.buffer) < 4:
                raise StopIteration

            if self.opcode in OPCODES['control']:
                raise ProtocolError('Control Frames are limited to 125 bytes')

            self.payload_len = struct.unpack('!H', self.buffer[2:4])[0]
            self.payload_start = 4

        elif self.payload_len == 127:
            if len(self.buffer) < 10:
                raise StopIteration

            if self.opcode in OPCODES['control']:
                raise ProtocolError('Control Frames are limited to 125 bytes')

            self.payload_len = struct.unpack('!Q', self.buffer[2:10])[0]
            self.payload_start = 10

    cdef process_payload(self):
        """
        The payload also inclueds the mask, if
        the data has been masked.

        Mask is 4 bytes, afterward the entire
        payload is sent.
        """
        if self.masked:
            self.payload_start += 4

        if len(self.buffer) < self.payload_start + self.payload_len:
            raise StopIteration

        self.data = self.buffer[
            self.payload_start:self.payload_start + self.payload_len]

        if self.masked:
            self.data = fast_mask(
                self.data,
                self.buffer[self.payload_start - 4:self.payload_start]
            )

    cdef process_frame(self):
        self.process_header()
        self.process_length()
        self.process_payload()

    def __len__(self):
        return self.payload_start + self.payload_len

    def __iter__(self):
        return self

    def __next__(self):
        if not self.buffer:
            raise StopIteration

        self.process_frame()

        return self


cpdef bytearray EncodeFrame(bytearray data,
                            int fin=1,
                            int opcode=OPCODES['binary'],
                            mask=False):
    """
    Encode a websocket packet before sending to
    the browser. Bytes are identical to the Frame
    class above.
    """
    cdef bytearray buffer = bytearray(2)
    cdef int length = 0

    # FIN Bit
    if fin:
        buffer[0] |= 0x80

    # Opcode
    buffer[0] |= opcode

    # Length
    length = len(data)
    if length <= 125:
        buffer[1] |= length

    elif length <= 65535:
        buffer[1] |= 126
        buffer.extend(struct.pack('!H', length))

    else:
        buffer[1] |= 127
        buffer.extend(struct.pack('!Q', length))

    # Mask bits
    if mask:
        buffer[1] |= 0x80

        buffer.extend(struct.pack('!I', random.getrandbits(32)))
        data = fast_mask(data, buffer[-4:])

    buffer.extend(data)

    return buffer
