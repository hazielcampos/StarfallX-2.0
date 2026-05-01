import struct
import time
import logging
from serial import Serial
from queue import Queue, Empty
from threading import Event
from src.shared import SharedData
from src.classes.Messages import *
logger = logging.getLogger(__name__)

# ─── Protocolo ────────────────────────────────────────────────────
SOF         = 0xAA
EOF_BYTE    = 0x55
MAX_PAYLOAD = 32

class SensorId:
    US1 = 0x00
    US2 = 0x01
    IR1 = 0x02
    IR2 = 0x03

SENSOR_NAMES = {
    SensorId.US1: "ultrasonic_1",
    SensorId.US2: "ultrasonic_2",
    SensorId.IR1: "ir_1",
    SensorId.IR2: "ir_2",
}

# ─── CRC-8 ────────────────────────────────────────────────────────
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
    header = bytes([SOF, msg_type, seq & 0xFF]) + struct.pack(">H", len(payload))
    body   = header + payload
    return body + bytes([crc8(body), EOF_BYTE])

# ─── Parser de trama ──────────────────────────────────────────────
class FrameParser:
    def __init__(self):
        self._buf      = bytearray()
        self._active   = False
        self._expected = 0

    def feed(self, byte: int) -> dict | None:
        if not self._active:
            if byte == SOF:
                self._active   = True
                self._expected = 0
                self._buf      = bytearray([byte])
            return None

        self._buf.append(byte)

        if len(self._buf) == 5:
            pay_len = struct.unpack(">H", bytes(self._buf[3:5]))[0]
            if pay_len > MAX_PAYLOAD:
                logger.warning(
                    "Parser: payload declarado demasiado grande (%d B), descartando trama",
                    pay_len,
                )
                self._reset()
                return {"error": "payload_too_large"}
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
            logger.warning(
                "Parser: EOF incorrecto (esperado 0x55, recibido 0x%02X)", eof
            )
            return {"error": "bad_eof"}

        calc = crc8(bytes(buf[:5 + pay_len]))
        if calc != rx_crc:
            logger.warning(
                "Parser: CRC incorrecto (calculado 0x%02X, recibido 0x%02X)", calc, rx_crc
            )
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
    PING_INTERVAL = 1.0

    def __init__(
        self,
        shared: SharedData,
        rx_queue: Queue,
        tx_queue: Queue,
        port: str,
        baudrate: int,
        stop_event: Event,
    ):
        self.shared     = shared
        self.rx_queue   = rx_queue
        self.tx_queue   = tx_queue
        self.stop_event = stop_event
        self._parser    = FrameParser()
        self._seq       = 0
        self._connected = False
        self._pending_ack: dict[int, float] = {}

        logger.info("Abriendo puerto %s a %d baudios...", port, baudrate)
        self.serial = Serial(port, baudrate, timeout=0)
        logger.info("Puerto serie abierto")

    # ── Envío interno ─────────────────────────────────────────────

    def _send_frame(self, msg_type: int, payload: bytes):
        seq   = self._seq
        frame = build_frame(msg_type, payload, seq)
        self.serial.write(frame)
        self._pending_ack[seq] = time.monotonic()
        self._seq = (self._seq + 1) & 0xFF
        logger.debug(
            "TX → [%s] seq=%d payload=%d B | raw=%s",
            MsgType.name(msg_type), seq, len(payload), frame.hex(),
        )

    def _send_ack(self, seq: int):
        frame = build_frame(MsgType.ACK, bytes([seq]), self._seq)
        self.serial.write(frame)
        logger.debug("TX → ACK para seq=%d", seq)
        self._seq = (self._seq + 1) & 0xFF

    def _send_nack(self):
        frame = build_frame(MsgType.NACK, b"", self._seq)
        self.serial.write(frame)
        logger.warning("TX → NACK enviado")
        self._seq = (self._seq + 1) & 0xFF

    # ── Lectura ───────────────────────────────────────────────────

    def read_payload(self) -> dict | None:
        waiting = self.serial.in_waiting
        if not waiting:
            return None

        logger.debug("RX: %d byte(s) disponibles en el buffer", waiting)

        for byte in self.serial.read(waiting):
            result = self._parser.feed(byte)
            if result is None:
                continue

            if "error" in result:
                logger.warning("Trama descartada: %s", result["error"])
                self._send_nack()
                return None

            logger.debug(
                "RX ← [%s] seq=%d payload=%d B",
                MsgType.name(result["type"]), result["seq"], len(result["payload"]),
            )
            return result

        return None

    # ── Procesamiento ─────────────────────────────────────────────

    def _process_frame(self, frame: dict):
        msg_type = frame["type"]
        seq      = frame["seq"]
        payload  = frame["payload"]

        if msg_type == MsgType.PING:
            self._send_ack(seq)
            if not self._connected:
                self._connected = True
                logger.info("✓ Handshake completado — ESP32 envió PING")

        elif msg_type == MsgType.ACK:
            acked_seq = payload[0] if payload else seq
            self._pending_ack.pop(acked_seq, None)
            logger.debug("ACK recibido para seq=%d (pendientes: %d)",
                         acked_seq, len(self._pending_ack))
            if not self._connected:
                self._connected = True
                logger.info("✓ Handshake completado — ACK de nuestro PING recibido")

        elif msg_type == MsgType.NACK:
            logger.warning("✗ NACK recibido de ESP32 (seq=%d) — posible error de trama", seq)

        elif msg_type == MsgType.DATA:
            self._send_ack(seq)
            self._handle_sensor(payload)

        elif msg_type == MsgType.CMD:
            self._send_ack(seq)
            if len(payload) >= 3 and payload[0] == 0x02:
                btn_id  = payload[1]
                state   = payload[2]
                name    = "btn_start" if btn_id == 0x00 else "btn_stop"
                pressed = (state == 0)
                logger.info("Botón [%s] → %s", name, "PRESIONADO" if pressed else "suelto")
                self.rx_queue.put_nowait({"button": name, "pressed": pressed})
            else:
                logger.warning(
                    "CMD recibido de ESP32 con payload inesperado: %s", payload.hex()
                )

        elif msg_type == MsgType.ERROR:
            self._send_ack(seq)
            logger.error("ERROR recibido de ESP32: payload=%s", payload.hex())

        else:
            logger.warning("Tipo desconocido: 0x%02X — enviando NACK", msg_type)
            self._send_nack()

    def _handle_sensor(self, payload: bytes):
        if len(payload) < 5:
            logger.warning(
                "Payload DATA demasiado corto: %d B (mínimo 5)", len(payload)
            )
            return

        sensor_id = payload[0]
        value     = struct.unpack("f", payload[1:5])[0]
        name      = SENSOR_NAMES.get(sensor_id, f"sensor_{sensor_id:#04x}")

        if sensor_id not in SENSOR_NAMES:
            logger.warning("ID de sensor desconocido: 0x%02X (valor=%.3f)", sensor_id, value)
        else:
            logger.debug("Sensor %-14s = %8.3f", name, value)
        if name in self.shared.data:
                with self.shared.lock:
                    self.shared.data[name] = value
        else:
            logger.warning("SharedData no tiene atributo '%s'", name)


    # ── Handshake ─────────────────────────────────────────────────

    def _do_handshake(self):
        logger.info("Iniciando handshake — esperando a ESP32...")
        last_ping  = 0.0
        ping_count = 0

        while not self._connected and not self.stop_event.is_set():
            now = time.monotonic()
            if now - last_ping >= self.PING_INTERVAL:
                ping_count += 1
                self._send_frame(MsgType.PING, b"")
                last_ping = now
                logger.info("PING #%d enviado — sin respuesta aún", ping_count)

            frame = self.read_payload()
            if frame:
                self._process_frame(frame)

            time.sleep(0.01)

        if not self._connected:
            logger.warning("Handshake cancelado por stop_event")

    # ── Loop principal ────────────────────────────────────────────

    def run(self):
        self._do_handshake()

        if not self._connected:
            return

        logger.info("CommsHandler operando — loop activo")
        frames_rx = 0
        frames_tx = 0

        while not self.stop_event.is_set():
            frame = self.read_payload()
            if frame:
                self._process_frame(frame)
                frames_rx += 1

            try:
                msg: Message = self.tx_queue.get_nowait()
                self._send_frame(msg.msg_type, msg.payload)
                frames_tx += 1
            except Empty:
                pass

            time.sleep(0.005)
        final_msg: Message = Message.drive(0.0, 0.0)
        self._send_frame(msg.msg_type, msg.payload)
        self.serial.close()
        logger.info(
            "CommsHandler detenido — total RX=%d TX=%d tramas", frames_rx, frames_tx
        )