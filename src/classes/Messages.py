import struct
from dataclasses import dataclass, field

class MsgType:
    CMD   = 0x01
    DATA  = 0x02
    ACK   = 0x03
    NACK  = 0x04
    PING  = 0x05
    ERROR = 0xFF

    _names = {0x01: "CMD", 0x02: "DATA", 0x03: "ACK",
              0x04: "NACK", 0x05: "PING", 0xFF: "ERROR"}

    @classmethod
    def name(cls, val: int) -> str:
        return cls._names.get(val, f"0x{val:02X}")

@dataclass
class Message:
    msg_type: int
    payload:  bytes = field(default=b"")

    @staticmethod
    def drive(v: float, w: float) -> "Message":
        # Añadimos el byte 0x01 al principio para que coincida con la ESP32
        payload = struct.pack("<Bff", 0x01, v, w) 
        return Message(msg_type=MsgType.CMD, payload=payload)
    
    @staticmethod
    def launc() -> "Message":
        payload = struct.pack("<B", 0x03)
        return Message(msg_type=MsgType.CMD, payload=payload)
    
    @staticmethod
    def servo(angle) -> "Message":
        payload = struct.pack("<BB", 0x03, angle)
        return Message(msg_type=MsgType.CMD, payload=payload)

    @staticmethod
    def ping() -> "Message":
        return Message(msg_type=MsgType.PING)

    @staticmethod
    def stop() -> "Message":
        return Message(msg_type=MsgType.CMD, payload=struct.pack("ff", 0.0, 0.0))