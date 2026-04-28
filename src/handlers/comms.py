import struct
import time
import logging
from serial import Serial
from queue import Queue, Empty
from threading import Event
from src.utils import SharedData
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─── Protocolo ────────────────────────────────────────────────────
SOF      = 0xAA
EOF_BYTE = 0x55
MAX_PAYLOAD = 32

class MsgType:
    CMD   = 0x01
    DATA  = 0x02
    ACK   = 0x03
    NACK  = 0x04
    PING  = 0x05
    ERROR = 0xFF

@dataclass
class Message:
    msg_type: int
    payload:  bytes = field(default=b"")

    # ── Constructores semánticos ──────────────────────────────────
    @staticmethod
    def drive(v: float, w: float) -> "Message":
        return Message(msg_type=MsgType.CMD, payload=struct.pack("ff", v, w))

    @staticmethod
    def ping() -> "Message":
        return Message(msg_type=MsgType.PING)

    @staticmethod
    def stop() -> "Message":
        return Message(msg_type=MsgType.CMD, payload=struct.pack("ff", 0.0, 0.0))

class SensorId:
    US1  = 0x00
    US2  = 0x01
    IR1  = 0x02
    IR2  = 0x03

SENSOR_NAMES = {
    SensorId.US1: "ultrasonic_1",
    SensorId.US2: "ultrasonic_2",
    SensorId.IR1: "ir_1",
    SensorId.IR2: "ir_2",
}

# ─── CRC-8 (polinomio 0x07) ───────────────────────────────────────
def crc8(data: bytes) -> int:
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc

# ─── Construcción de tramas ───────────────────────────────────────
def build_frame(msg_type: int, payload: bytes, seq: int) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        payload = payload[:MAX_PAYLOAD]
    header  = bytes([SOF, msg_type, seq & 0xFF]) + struct.pack(">H", len(payload))
    body    = header + payload
    return body + bytes([crc8(body), EOF_BYTE])

# ─── Parser de trama ──────────────────────────────────────────────
class FrameParser:
    """
    Máquina de estados no-bloqueante. Se alimenta byte a byte con feed()
    y devuelve un dict cuando la trama está completa y válida.
    """
    def __init__(self):
        self._buf      = bytearray()
        self._active   = False
        self._expected = 0   # longitud total esperada de la trama

    def feed(self, byte: int) -> dict | None:
        if not self._active:
            if byte == SOF:
                self._active   = True
                self._expected = 0
                self._buf      = bytearray([byte])
            return None

        self._buf.append(byte)

        # Con 5 bytes de cabecera ya sabemos el tamaño del payload
        if len(self._buf) == 5:
            pay_len = struct.unpack(">H", bytes(self._buf[3:5]))[0]
            if pay_len > MAX_PAYLOAD:
                self._reset()
                return {"error": "payload_too_large"}
            # total = 5 (cabecera) + pay_len + 1 (CRC) + 1 (EOF)
            self._expected = 5 + pay_len + 2

        if self._expected > 0 and len(self._buf) == self._expected:
            return self._validate()

        return None

    def _validate(self) -> dict:
        buf = self._buf
        self._reset()

        pay_len = struct.unpack(">H", bytes(buf[3:5]))[0]
        rx_crc  = buf[5 + pay_len]
        eof     = buf[6 + pay_len]

        if eof != EOF_BYTE:
            return {"error": "bad_eof"}

        if crc8(bytes(buf[:5 + pay_len])) != rx_crc:
            return {"error": "bad_crc"}

        return {
            "type":    buf[1],
            "seq":     buf[2],
            "payload": bytes(buf[5:5 + pay_len]),
        }

    def _reset(self):
        self._buf      = bytearray()
        self._active   = False
        self._expected = 0


# ─── Handler principal ────────────────────────────────────────────
class CommsHandler:
    PING_INTERVAL = 1.0   # segundos entre pings durante handshake

    def __init__(
        self,
        shared: SharedData,
        rx_queue: Queue,
        tx_queue: Queue,
        port: str,
        baudrate: int,
        stop_event: Event,
    ):
        self.shared      = shared
        self.rx_queue    = rx_queue
        self.tx_queue    = tx_queue
        self.serial      = Serial(port, baudrate, timeout=0)  # non-blocking
        self.stop_event  = stop_event
        self._parser     = FrameParser()
        self._seq        = 0
        self._connected  = False
        self._pending_ack: dict[int, float] = {}  # seq → timestamp de envío

    # ── API pública ───────────────────────────────────────────────

    def send_drive(self, v: float, w: float):
        """Encola un comando de movimiento (v, w) hacia la ESP32."""
        payload = struct.pack("ff", v, w)
        self.tx_queue.put_nowait((MsgType.CMD, payload))

    def send_ping(self):
        self.tx_queue.put_nowait((MsgType.PING, b""))

    # ── Envío interno ─────────────────────────────────────────────

    def _send_frame(self, msg_type: int, payload: bytes):
        seq   = self._seq
        frame = build_frame(msg_type, payload, seq)
        self.serial.write(frame)
        self._pending_ack[seq] = time.monotonic()
        self._seq = (self._seq + 1) & 0xFF
        logger.debug("TX  type=0x%02X seq=%d len=%d", msg_type, seq, len(payload))

    def _send_ack(self, seq: int):
        frame = build_frame(MsgType.ACK, bytes([seq]), self._seq)
        self.serial.write(frame)
        self._seq = (self._seq + 1) & 0xFF

    def _send_nack(self):
        frame = build_frame(MsgType.NACK, b"", self._seq)
        self.serial.write(frame)
        self._seq = (self._seq + 1) & 0xFF

    # ── Lectura y parsing ─────────────────────────────────────────

    def read_payload(self) -> dict | None:
        """
        Lee todos los bytes disponibles en el puerto serie y los pasa
        al parser. Devuelve la primera trama válida encontrada, o None.
        """
        waiting = self.serial.in_waiting
        if not waiting:
            return None

        for byte in self.serial.read(waiting):
            result = self._parser.feed(byte)
            if result is None:
                continue

            if "error" in result:
                logger.warning("Frame error: %s", result["error"])
                self._send_nack()
                return None

            return result

        return None

    # ── Procesamiento de trama entrante ───────────────────────────

    def _process_frame(self, frame: dict):
        msg_type = frame["type"]
        seq      = frame["seq"]
        payload  = frame["payload"]

        logger.debug("RX  type=0x%02X seq=%d len=%d", msg_type, seq, len(payload))

        if msg_type == MsgType.PING:
            # ESP32 pidió handshake — confirmar y marcar conexión
            self._send_ack(seq)
            if not self._connected:
                self._connected = True
                logger.info("Handshake completado (recibimos PING de ESP32)")

        elif msg_type == MsgType.ACK:
            # Confirmar que nuestro PING llegó bien
            acked_seq = payload[0] if payload else seq
            self._pending_ack.pop(acked_seq, None)
            if not self._connected:
                self._connected = True
                logger.info("Handshake completado (ACK de nuestro PING recibido)")

        elif msg_type == MsgType.NACK:
            logger.warning("NACK recibido de ESP32 (seq=%d)", seq)

        elif msg_type == MsgType.DATA:
            self._send_ack(seq)
            self._handle_sensor(payload)
        elif msg_type == MsgType.CMD:
            self._send_ack(seq)
            if len(payload) >= 3 and payload[0] == 0x02:  # CMD_BTN
                btn_id = payload[1]
                state  = payload[2]
                name   = "btn_start" if btn_id == 0x00 else "btn_stop"
                # LOW = presionado (INPUT_PULLUP), HIGH = suelto
                pressed = (state == 0)
                self.rx_queue.put_nowait({"button": name, "pressed": pressed})

        elif msg_type == MsgType.ERROR:
            self._send_ack(seq)
            logger.error("ERROR recibido de ESP32: payload=%s", payload.hex())

        else:
            logger.warning("Tipo de mensaje desconocido: 0x%02X", msg_type)
            self._send_nack()

    def _handle_sensor(self, payload: bytes):
        """Parsea un MSG_DATA y publica el valor en shared y en rx_queue."""
        if len(payload) < 5:
            logger.warning("Payload DATA demasiado corto: %d bytes", len(payload))
            return

        sensor_id = payload[0]
        value     = struct.unpack("f", payload[1:5])[0]
        name      = SENSOR_NAMES.get(sensor_id, f"sensor_{sensor_id:#04x}")

        logger.debug("Sensor %s = %.3f", name, value)

        # Actualizar SharedData si tiene esa clave
        if hasattr(self.shared.data, name):
            setattr(self.shared.data, name, value)

        # También publicar en la rx_queue para otros consumidores
        self.rx_queue.put_nowait({"sensor": name, "value": value})

    # ── Handshake ─────────────────────────────────────────────────

    def _do_handshake(self):
        """
        Bloquea hasta que la ESP32 confirme la conexión.
        Envía PING periódicamente y procesa cualquier trama entrante.
        """
        logger.info("Esperando a ESP32...")
        last_ping = 0.0

        while not self._connected and not self.stop_event.is_set():
            now = time.monotonic()
            if now - last_ping >= self.PING_INTERVAL:
                self._send_frame(MsgType.PING, b"")
                last_ping = now
                logger.debug("PING enviado")

            frame = self.read_payload()
            if frame:
                self._process_frame(frame)

            time.sleep(0.01)

        if self._connected:
            logger.info("ESP32 conectada — iniciando operación normal")

    # ── Loop principal ────────────────────────────────────────────

    def run(self):
        self._do_handshake()

        while not self.stop_event.is_set():
            # 1. Leer datos entrantes de la ESP32
            frame = self.read_payload()
            if frame:
                self._process_frame(frame)

            # 2. Enviar comandos pendientes en la tx_queue
            try:
                msg: Message = self.tx_queue.get_nowait()
                self._send_frame(msg.msg_type, msg.payload)
            except Empty:
                pass

            # 3. Detectar desconexión si no llega nada en mucho tiempo
            #    (opcional: puedes activar esto si lo necesitas)
            # self._check_timeout()

            time.sleep(0.005)

        logger.info("CommsHandler detenido")