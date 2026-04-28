import struct

START = 0xAA
END = 0x55

class MessageType:
    ULTRASONIC = 1
    SPEED = 2
    IR = 3

class Message:

    def __init__(self, emitter_id, type: MessageType, value):
        self.emitter = emitter_id # <- if you have more than 1 ultrasonic or ir you are gonna need to identify witch one is sending the msg
        self.type = type
        self.value = value # <- message value can be any number, for floats required use 0 and 1 and it should let you use floats for sensor data.

    def encode(self): # <- when you create a Message object and call this function it returns the Message encoded into binary (so you can send it to the MCU)
        return struct.pack(
            '>BBBfB',
            START,
            self.emitter,
            self.type,
            self.value,
            END
        )

    def decode(data: bytes): # <- receive a binary message and decode it into a Message object to be processed.
        try:
            start, emitter, msg_type, value, end = struct.unpack('>BBBfB', data)
            if start != START or end !=END:
                raise ValueError("Invalid message format")
            
            return Message(
                emitter, MessageType(msg_type), value
            )
        except Exception as e:
            print("Decode error:", e)
            return None