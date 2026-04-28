from queue import Queue, Empty
from time import sleep
from utils import SharedData
from threading import Event
from handlers.comms import Message, MsgType

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

        # Último valor conocido de cada sensor — se actualiza cada ciclo
        self._sensors: dict[str, float] = {
            "ultrasonic_1": -1.0,
            "ultrasonic_2": -1.0,
            "ir_1":          0.0,
            "ir_2":          0.0,
        }

    def _collect_sensors(self) -> int:
        count = 0
        while True:
            try:
                msg: dict = self.rx_queue.get_nowait()
                if "sensor" in msg and msg["sensor"] in self._sensors:
                    self._sensors[msg["sensor"]] = msg["value"]
                    count += 1
                elif "button" in msg:
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
        d1  = self._sensors["ultrasonic_1"]
        d2  = self._sensors["ultrasonic_2"]
        ir1 = self._sensors["ir_1"]
        ir2 = self._sensors["ir_2"]

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