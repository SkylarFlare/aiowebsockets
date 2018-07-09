import struct
import random

from .exception import IncompleteFrame
from .exception import ProtocolError
from .constants import OPCODES

try:
    from .fast_mask import fast_mask

except ImportError:
    from .utils import fast_mask


class Frame:

    def __init__(self, buffer):
        self.parse_header(buffer)
        self.parse_length(buffer)
        self.parse_payload(buffer)

    def parse_header(self, buffer):
        """
        byte 1 consists of
         - fin (Last Frame)
         - rsv1, rsv2, rsv3 (Reserved bits)
         - Opcode (Operation code)
        """
        if len(buffer) < 2:
            raise IncompleteFrame

        self.fin = True if buffer[0] & 0b10000000 else False
        self.opcode = buffer[0] & 0b00001111
        self.masked = True if buffer[1] & 0b10000000 else False
        self.rsv = (
            True if buffer[0] & 0b01000000 else False,
            True if buffer[0] & 0b00100000 else False,
            True if buffer[0] & 0b00010000 else False,
        )

        if self.rsv[0] or self.rsv[1] or self.rsv[2]:
            raise ProtocolError('RSV Must be 0')

        if self.opcode not in OPCODES.values():
            raise ProtocolError('OPCODE is not implemented')

    def parse_length(self, buffer):
        """
        byte 2 consists of
         - Masked (whether the data is masked)
         - Payload Length
        """
        self.payload_len = buffer[1] & 0b01111111
        self.mask_start, self.payload_start = 2, 2

        if self.payload_len == 126:
            if len(buffer) < 4:
                raise IncompleteFrame

            self.payload_len = struct.unpack('!H', buffer[2:4])[0]
            self.mask_start, self.payload_start = 4, 4

        elif self.payload_len == 127:
            if len(buffer) < 10:
                raise IncompleteFrame

            self.payload_len = struct.unpack('!Q', buffer[2:10])[0]
            self.mask_start, self.payload_start = 10, 10

        # Make sure control frames are 2 bytes
        if self.opcode in OPCODES['control'] and self.payload_len > 125:
            raise ProtocolError("Control frames can't exceed 125 bytes")

    def parse_payload(self, buffer):
        """
        The payload also includes the mask, if
        the data has been Masked (See byte 2).

        Mask is 4 bytes, afterwards the entire
        payload is sent
        """
        mask_keys = [0] * 4

        if self.masked:
            if len(buffer) < self.mask_start + 4:
                raise IncompleteFrame

            self.payload_start = self.mask_start + 4
            mask_keys = buffer[self.mask_start:self.mask_start + 4]

        # Make sure we have enough data in our buffer
        if self.payload_start + self.payload_len > len(buffer):
            raise IncompleteFrame

        # Now we can read and decode our frame
        self.byte_data = buffer[
            self.payload_start:self.payload_start + self.payload_len]

        if self.masked:
            self.byte_data = fast_mask(self.byte_data, mask_keys)

    def __len__(self):
        """
        Returns the frame length so that it can be stripped
        from the receive buffer
        """
        return self.payload_start + self.payload_len


def EncodeFrame(B_FIN, OPCODE, data, mask=False):
    """
    Encode a websocket packet before sending to
    the browser. Bytes are identical to the Frame
    class above.
    """
    header, body = bytearray(), bytearray()
    b0, b1 = 0, 0

    if B_FIN:
        b0 |= 0x80

    b0 |= OPCODE
    header.append(b0)

    if mask:
        b1 |= 0x80

    length = len(data)
    if length <= 125:
        b1 |= length
        header.append(b1)

    elif length >= 126 and length <= 65535:
        b1 |= 126
        header.append(b1)
        header.extend(struct.pack("!H", length))

    else:
        b1 |= 127
        header.append(b1)
        header.extend(struct.pack("!Q", length))

    if mask:
        if not isinstance(data, bytearray):
            data = bytearray(data)

        mask_bits = struct.pack("!I", random.getrandbits(32))
        header.extend(mask_bits)
        data = fast_mask(data, bytearray(mask_bits))

    body.extend(header)
    body.extend(data)

    return body
