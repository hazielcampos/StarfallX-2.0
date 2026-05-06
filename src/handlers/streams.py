import socket
import struct
import cv2
import threading
import logging
from time import sleep
from src.config.loader import ConfigManager
from src.shared import SharedData, Data
from src.config import ConfigManager
logger = logging.getLogger(__name__)

# Protocolo de frames: [1 byte stream_id][jpeg data]
FRAME_HEADER_FMT = '>B'
FRAME_HEADER_SIZE = struct.calcsize(FRAME_HEADER_FMT)
MAX_PAYLOAD = 65000 - FRAME_HEADER_SIZE

# Protocolo de comandos LAB (recibidos desde PC):
#   [1 byte tipo=0xAB][6 x uint16 big-endian]
#   orden: lower_L, lower_A, lower_B, upper_L, upper_A, upper_B
CMD_MAGIC = 0xAB
CMD_FMT = '>B6H'          # 1 byte + 6 uint16
CMD_SIZE = struct.calcsize(CMD_FMT)

STREAM_PORT = 9999        # envío de frames
CMD_PORT    = 9998        # recepción de comandos LAB


class StreamsHandler:
    def __init__(self, shared: SharedData, config_manager: ConfigManager,  stop_event, dest_ip="10.12.3.10"):
        self.shared = shared
        self.config_manager = config_manager
        self.stop_event = stop_event
        self.dest_ip = dest_ip

    # ------------------------------------------------------------------ #
    #  Sockets                                                             #
    # ------------------------------------------------------------------ #
    def _init_sockets(self):
        # UDP send (frames → PC)
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.stream_addr = (self.dest_ip, STREAM_PORT)

        # UDP recv (comandos LAB ← PC)
        self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.cmd_sock.bind(("0.0.0.0", CMD_PORT))
        self.cmd_sock.settimeout(1.0)

    # ------------------------------------------------------------------ #
    #  Envío de un frame                                                   #
    # ------------------------------------------------------------------ #
    def _send_frame(self, stream_id: int, frame):
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
        _, buffer = cv2.imencode('.jpg', frame, encode_params)
        data = buffer.tobytes()
        if len(data) > MAX_PAYLOAD:
            return
        header = struct.pack(FRAME_HEADER_FMT, stream_id)
        self.send_sock.sendto(header + data, self.stream_addr)

    # ------------------------------------------------------------------ #
    #  Hilo: recepción de comandos LAB                                     #
    # ------------------------------------------------------------------ #
    def _cmd_loop(self):
        logger.info(f"CMD listener en puerto {CMD_PORT}")
        while not self.stop_event.is_set():
            try:
                data, _ = self.cmd_sock.recvfrom(512)
                if len(data) != CMD_SIZE:
                    continue
                unpacked = struct.unpack(CMD_FMT, data)
                magic = unpacked[0]
                if magic != CMD_MAGIC:
                    continue
                #vals = list(unpacked[1:])   # [lL, lA, lB, uL, uA, uB]
                #lower = vals[:3]
                #upper = vals[3:]
                #self.shared.set_lab_bounds(lower, upper)
                #logger.debug(f"LAB actualizado: lower={lower} upper={upper}")
            except socket.timeout:
                continue
            except Exception as e:
                logger.warning(f"CMD recv error: {e}")

    # ------------------------------------------------------------------ #
    #  Loop principal                                                      #
    # ------------------------------------------------------------------ #
    def run(self):
        self._init_sockets()

        cmd_thread = threading.Thread(target=self._cmd_loop, daemon=True)
        cmd_thread.start()

        logger.info(f"Streaming → {self.dest_ip}:{STREAM_PORT}")
        while not self.stop_event.is_set():
            frames = {stream_id: self.shared.get_frame(stream_id) for stream_id in self.shared.frames}

            for stream_id, frame in frames.items():
                self._send_frame(stream_id, frame)

            sleep(1 / 24)

        self.send_sock.close()
        self.cmd_sock.close()
        logger.info("StreamsHandler terminado.")
