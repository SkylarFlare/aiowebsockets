class IncompleteFrame(Exception):
    pass


class ProtocolError(Exception):
    pass


class BufferExceeded(Exception):
    pass


class CloseFrame(Exception):
    def __init__(self, status, reason):
        self.type = type
        self.status = status
        self.reason = reason

    def __str__(self):
        return self.reason
