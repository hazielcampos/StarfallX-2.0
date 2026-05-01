from queue import Queue, Empty
from time import sleep, time
from src.shared import SharedData
from threading import Event
from src.classes.Messages import *
from enum import Enum
import random
import logging

logger = logging.getLogger(__name__)

class State(Enum):
    IDLE = 0
    BALL_SEARCH   = 1 # busqueda de balon
    BALL_APROACH  = 2 
    FRAME_SEARCH   = 3
    FRAME_APROACH  = 4
    SHOOT  = 5
    AVOID_OBSTACLE = 6

class ControlHandler:
    state = State.IDLE
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
        self.started = False
        self._prev_error = 0
        self._integral = 0

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
    def _pid(self, kp, kd, ki, error):
        # Normalizar error (-100 a 100) -> (-1 a 1)
        e = error / 100.0

        # Derivada
        derivative = e - self._prev_error

        # Integral (con anti-windup básico)
        self._integral += e
        self._integral = max(min(self._integral, 1), -1)

        # PID
        w = kp * e + kd * derivative + ki * self._integral

        # Saturar salida angular
        w = max(min(w, 1), -1)

        # Velocidad lineal:
        # entre más error, menos avance (para no irte de largo)
        v = 1.0 - abs(e)

        # Permitir reversa si el error es muy grande (opcional)
        if abs(e) > 0.9:
            v = -0.3

        # Saturar
        v = max(min(v, 1), -1)

        # Guardar estado
        self._prev_error = e

        return v, w

    def _handle_button(self, name: str, pressed: bool):
        if name == "btn_start" and pressed:
            self.running.set()
        elif name == "btn_stop" and pressed:
            self.running.clear()
            self.tx_queue.put_nowait(Message.stop())
    
    def _send_speed(self, v: float, w: float):
        self.tx_queue.put_nowait(Message.drive(v, w))


    def _search_ball(self):
        _internal_ball_on_view = False
        with self.shared.lock:
            _internal_ball_on_view = self.shared.data["ball_on_view"]
        direction = random.choice([-1, 1])
        start_time = time()
        while not _internal_ball_on_view:
            if time() - start_time  > 3:
                direction = direction*-1
                start_time = time()
            self._send_speed(0.0, 0.5*direction)

            with self.shared.lock:
                _internal_ball_on_view = self.shared.data["ball_on_view"]
        self._send_speed(0.0, 0.0)
        self.state = State.BALL_APROACH

    def _aproach_ball(self):
        with self.shared.lock:
            error = self.shared.data["ball_x"]
        return self._pid(1, 0.05, 0.001, error)
        

    # ── Lógica de control — trabaja con self._sensors completo ──────
    def _compute_control(self) -> tuple[float, float]:
        with self.shared.lock:
            d1 = self.shared.data["ultrasonic_1"]
            d2 = self.shared.data["ultrasonic_2"]
            ir1 = self.shared.data["ir_1"]
            ir2 = self.shared.data["ir_2"]
        with self.shared.lock:
            _internal_ball_on_view = self.shared.data["ball_on_view"]
        print(_internal_ball_on_view)
        if _internal_ball_on_view:
            return self._aproach_ball()
        return 0, 0

    def run(self):
        while not self.stop_event.is_set():
            #if not self.running.is_set():
            #   sleep(0.1)
            #   continue

            # 1. Recoger todos los sensores disponibles en este ciclo
            self._collect_sensors()

            # 2. Calcular con el snapshot completo y más reciente
            v, w = self._compute_control()

            # 3. Encolar comando hacia la ESP32
            self.tx_queue.put_nowait(Message.drive(v, w))

            print(v, w)

            sleep(0.05)   # frecuencia del loop de control ~20 Hz
        logger.info("Control module finished.")