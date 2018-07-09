class Flags:
    AWAITING_HANDSHAKE = 0b00000000
    HANDSHAKE_COMPLETE = 0b00000001
    FRAGMENTATION_STARTED = 0b00000010
    MASK_DATA = 0b00000100


# 1MB Max Buffer Size
MAX_BUFFER_LENGTH = 1024 * 1024

STATUS_CODES = {
    'close': 1000,
    'going-away': 1001,
    'protocol-error': 1002,
    'bad-type': 1003,
    # 'reserved-1004': 1004,
    # 'reserved-1005': 1005,
    # 'reserved-1006': 1006,
    'inconsistent-type': 1007,
    'policy-violation': 1008,
    'buffer-exceeded': 1009,
    'unsupported-extension': 1010,
    'unexpected-exception': 1011,
    # 'reserved-1015': 1015,
    'reserved-3000': 3000,
    'reserved-3999': 3999,
    'reserved-4000': 4000,
    'reserved-4999': 4999,
}

VALID_STATUS_CODES = STATUS_CODES.values()

OPCODES = {
    "stream": 0x00,
    "text": 0x01,
    "binary": 0x02,
    "close": 0x08,
    "ping": 0x09,
    "pong": 0x0a,
    "control": (0x08, 0x09, 0x0a)
}
