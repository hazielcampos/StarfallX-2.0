from queue import Queue, Empty
from time import sleep
from src.utils import SharedData
from threading import Event
from .comms import Message, MsgType

class ControlHandler:
    def __init__(
        self,
        shared: SharedData,
        rx_queue: Queue,
        tx_queue: Queue,
        stop_event: Event,
        running: Event,
    ):
        self.rx_queue   = rx_queue
        self.tx_queue   = tx_queue
        self.shared     = shared
        self.stop_event = stop_event
        self.running    = running

    def _collect_sensors(self) -> int:
        count = 0
        while True:
            try:
                msg: dict = self.rx_queue.get_nowait()
                if "button" in msg:
                    self._handle_button(msg["button"], msg["pressed"])
                    count += 1
            except Empty:
                break
        return count

    def _handle_button(self, name: str, pressed: bool):
        if name == "btn_start" and pressed:
            self.running.set()
        elif name == "btn_stop" and pressed:
            self.running.clear()
            self.tx_queue.put_nowait(Message.stop())

    # ── Lógica de control — trabaja con self._sensors completo ──────
    def _compute_control(self) -> tuple[float, float]:
        with self.shared.lock:
            d1 = self.shared.data["ultrasonic_1"]
            d2 = self.shared.data["ultrasonic_2"]
            ir1 = self.shared.data["ir_1"]
            ir2 = self.shared.data["ir_2"]

        # Ejemplo: parar si hay obstáculo a menos de 15 cm
        """ if 0 < d1 < 15 or 0 < d2 < 15:
            return 0.0, 0.0

        # Ejemplo: corrección lateral con IR
        error = ir1 - ir2
        v = 0.5
        w = error * 0.001   # ganancia proporcional """

        return 1.0, 0

    def run(self):
        while not self.stop_event.is_set():
            if not self.running.is_set():
                sleep(0.1)
                continue

            # 1. Recoger todos los sensores disponibles en este ciclo
            self._collect_sensors()

            # 2. Calcular con el snapshot completo y más reciente
            v, w = self._compute_control()

            # 3. Encolar comando hacia la ESP32
            self.tx_queue.put_nowait(Message.drive(v, w))

            sleep(0.05)   # frecuencia del loop de control ~20 Hz