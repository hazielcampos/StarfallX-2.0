import socket
import struct
import cv2
from queue import Queue, Empty
from time import sleep
from src.utils import SharedData

class StreamsHandler:
    HEADER_FORMAT = '>B'        # unsigned int 4 bytes, big-endian
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_PAYLOAD = 65000 - HEADER_SIZE

    def __init__(self, shared: SharedData, stop_event):
        self.shared = shared
        self.stop_event = stop_event

    def __init_stream__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = ("10.12.3.10", 9999)

    def _send_frame(self, id, frame):
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        data = buffer.tobytes()

        if len(data) > self.MAX_PAYLOAD:
            return

        header = struct.pack(self.HEADER_FORMAT, id)
        self.sock.sendto(header + data, self.addr)

    def run(self):
        self.__init_stream__()
        while not self.stop_event.is_set():
            with self.shared.lock:
                frames = dict(self.shared.frames)  # copia para no bloquear mientras envías
            for id, frame in frames.items():
                self._send_frame(id, frame)
            sleep(1/24)
                