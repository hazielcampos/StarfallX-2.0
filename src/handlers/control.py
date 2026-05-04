from queue import Queue, Empty
from time import sleep, time
from src.shared import SharedData
from threading import Event
from src.classes.Messages import *
from enum import Enum
import random
import logging

logger = logging.getLogger(__name__)

IR_TRESHOLD = 5

class State(Enum):
    IDLE = 0
    BALL_SEARCH   = 1
    BALL_APPROACH  = 2 
    FRAME_SEARCH   = 3
    FRAME_APPROACH  = 4
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
        self.state = State.IDLE
        self.last_switch_time = 0
    
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

    def _send_speed(self, v: float, w: float):
        self.tx_queue.put_nowait(Message.drive(v, w))

    def _state_idle(self):
        #self._send_speed(0.0, 0.0)
        pass

    def _state_search_ball(self):
        logger.info("STARTING SEARCH")
        _internal_ball_on_view = False
        with self.shared.lock:
            _internal_ball_on_view = self.shared.data["ball_on_view"]
        direction = random.choice([-1, 1])
        start_time = time()
        while not _internal_ball_on_view:
            if not self.running.is_set():
               break
            if time() - start_time  > 3:
                direction = direction*-1
                start_time = time()
            self._send_speed(0.0, direction)

            with self.shared.lock:
                _internal_ball_on_view = self.shared.data["ball_on_view"]
        self._send_speed(0.0, 0.0)
        logger.info("Ball found, starting search")
        self.state = State.BALL_APPROACH

    def _state_approach_ball(self):
        logger.info("Approaching ball")
        _internal_ball_on_view = False
        _internal_ir_value = 0.0
        with self.shared.lock:
            _internal_ball_on_view = self.shared.data["ball_on_view"]
            _internal_ir_value = self.shared.data["ir_1"]
            error = self.shared.data["ball_x"]
        if (not _internal_ir_value < IR_TRESHOLD) and _internal_ball_on_view:
            v, w = self._pid(1, 0.05, 0.001, error)
            self._send_speed(v, w)
        elif _internal_ir_value < IR_TRESHOLD and not _internal_ball_on_view: 
            self.state = State.FRAME_SEARCH
            logger.info("SEARCHING FRAME")
        elif not _internal_ball_on_view:
            self.state = State.BALL_SEARCH

    def _state_frame_search(self):
        _internal_goal_on_view = False
        _internal_ir_value = 0.0
        with self.shared.lock:
            _internal_goal_on_view = self.shared.data["goal_on_view"]
            _internal_ir_value = self.shared.data["ir_1"]

        direction = random.choice([-0.6, 0.6])
        start_time = time()
        while not _internal_goal_on_view:
            if not self.running.is_set():
               break

            if _internal_ir_value > IR_TRESHOLD:
                self.state = State.BALL_SEARCH
                break

            if time() - start_time  > 3:
                direction = direction*-1
                start_time = time()
            self._send_speed(0.0, direction)

            with self.shared.lock:
                _internal_goal_on_view = self.shared.data["goal_on_view"]
                _internal_ir_value = self.shared.data["ir_1"]

        self._send_speed(0.0, 0.0)
        self.state = State.FRAME_APPROACH
    
    def _state_frame_approach(self):
        _internal_goal_on_view = False
        _internal_ir_value = 0.0
        _internal_line_limit = False
        with self.shared.lock:
            _internal_goal_on_view = self.shared.data["goal_on_view"]
            _internal_ir_value = self.shared.data["ir_1"]
            _internal_line_limit = self.shared.data["line_limit"]
            error = self.shared.data["goal_x"]
        if (not _internal_ir_value < IR_TRESHOLD) and _internal_goal_on_view and not _internal_line_limit:
            v, w = self._pid(1, 0.05, 0.001, error)
            self._send_speed(v, w)
        elif _internal_line_limit:
            self.state = State.SHOOT
        elif _internal_ir_value < IR_TRESHOLD:
            self.state = State.FRAME_APPROACH
        elif not _internal_goal_on_view:
            self.state = State.BALL_SEARCH

    def _state_shoot(self):
        self.tx_queue.put_nowait(Message.servo(90))
        self.state = State.IDLE

    def run(self):
        actions = {
            State.IDLE: self._state_idle,
            State.BALL_SEARCH: self._state_search_ball,
            State.BALL_APPROACH: self._state_approach_ball,
            State.FRAME_SEARCH: self._state_frame_search,
            State.FRAME_APPROACH: self._state_frame_approach,
            State.SHOOT: self._state_shoot
        }
        while not self.stop_event.is_set():

            if not self.running.is_set():
               if self.state != State.IDLE:
                    self.state = State.IDLE
                    logger.info("Robot stopped, state change -> IDLE")
               #self._send_speed(0.0, 0.0)
            else:
                if self.state == State.IDLE:
                    self.state = State.BALL_SEARCH
                    logger.info("Robot started and running, state change -> BALL SEARCH")
                
            actions[self.state]()
            sleep(0.05)   # frecuencia del loop de control ~20 Hz
        logger.info("Control module finished.")