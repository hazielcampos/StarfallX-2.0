from queue import Queue, Empty
from time import sleep, time
from src.shared import SharedData
from threading import Event
from src.classes.Messages import *
from enum import Enum
import random
import logging

logger = logging.getLogger(__name__)

IR_TRESHOLD = 2600
IR2_TRESHOLD = 2700

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
        self.last_direction = random.choice([-0.6, 0.6])
        self.start_search_time = 0

    def _has_ball(self) -> bool:
        with self.shared.lock:
            ball_size = self.shared.data["ball_size"]
            ball_y = self.shared.data["ball_y"]
        
        if ball_size > 10000 or ball_y > 415:
            return True
        return False
    

    def _pid(self, kp, kd, ki, error):
        # Normalizar error (-100 a 100) -> (-1 a 1)
        e = error / 100.0

        # Derivada
        derivative = e - self._prev_error

        # Integral (con anti-windup básico)
        self._integral += e
        self._integral = max(min(self._integral, 0.6), -0.6)

        # PID
        w = kp * e + kd * derivative + ki * self._integral

        # Saturar salida angular
        w = max(min(w, 0.6), -0.6)

        # Velocidad lineal:
        # entre más error, menos avance (para no irte de largo)
        v = 0.6 - abs(e)

        # Permitir reversa si el error es muy grande (opcional)
        if abs(e) > 0.9:
            v = -0.3

        # Saturar
        v = max(min(v, 0.6), -0.6)

        # Guardar estado
        self._prev_error = e

        return v, w 

    def _send_speed(self, v: float, w: float):
        self.tx_queue.put_nowait(Message.drive(v, w))

    def _state_idle(self):
        logger.info("idle")
        self._send_speed(0.0, 0.0)
        self.tx_queue.put_nowait(Message.servo(180))
        

    def _state_search_ball(self):
        logger.info("Searching ball")

        with self.shared.lock:
            _internal_ball_on_view = self.shared.data["ball_on_view"]

        if not _internal_ball_on_view:
            if self.start_search_time == 0:
                logger.info("Searching...")
                self.start_search_time = time()

            if time() - self.start_search_time > 6 and not _internal_ball_on_view:
                self.last_direction = self.last_direction * -1
                self.start_search_time = time()
                return
            self._send_speed(0.0, self.last_direction)
        else:
            self._send_speed(0.4, 0.0)
            self.start_search_time = 0
            self.last_direction = random.choice([-0.4, 0.4])
            logger.info("Ball found, starting approach")
            self.state = State.BALL_APPROACH

    def _state_approach_ball(self):
        logger.info("Approaching ball")
        _internal_ball_on_view = False
        with self.shared.lock:
            _internal_ball_on_view = self.shared.data["ball_on_view"]
            _internal_goal_on_view = self.shared.data["goal_on_view"]
            error = self.shared.data["ball_x"]

        if (not self._has_ball()) and _internal_ball_on_view:
            v, w = self._pid(1, 0.05, 0.0, error)
            self._send_speed(v, w)
        
        elif _internal_goal_on_view and self._has_ball():
            self.state = State.FRAME_APPROACH

        elif self._has_ball() and not _internal_ball_on_view: 
            self.state = State.FRAME_SEARCH
        elif not _internal_ball_on_view and not self._has_ball():
            self.state = State.BALL_SEARCH

    def _state_frame_search(self):
        logger.info("Searching frame")

        _internal_goal_on_view = False
        with self.shared.lock:
            _internal_goal_on_view = self.shared.data["goal_on_view"]
            _internal_ball_on_view = self.shared.data["ball_on_view"]

        if self.start_search_time == 0:
            self.start_search_time = time()
        if not self._has_ball() and not _internal_ball_on_view:
            self.state = State.BALL_SEARCH
            return
        if not _internal_goal_on_view:
            if time() - self.start_search_time  > 4:
                self.last_direction = self.last_direction*-1
                self.start_search_time = time()
            else:
                self._send_speed(0.0, self.last_direction)
        else:
            self.start_search_time = 0
            self.last_direction = random.choice([-0.3, 0.3])
            self._send_speed(0.0, 0.0)
            self.state = State.FRAME_APPROACH
    
    def _state_frame_approach(self):
        logger.info("Approaching frame")
        _internal_goal_on_view = False
        _internal_line_limit = False
        with self.shared.lock:
            _internal_goal_on_view = self.shared.data["goal_on_view"]
            _internal_ball_on_view = self.shared.data["ball_on_view"]
            _internal_line_limit = self.shared.data["line_limit"]
            error_ball = self.shared.data["ball_x"]
            error = self.shared.data["goal_x"]
            ultrasonic = self.shared.data["ultrasonic_1"]
        
        if (ultrasonic < 35) and _internal_goal_on_view and (self._has_ball() or _internal_ball_on_view):
            self.state = State.SHOOT
        elif (ultrasonic < 32) and _internal_goal_on_view:
            self.state = State.SHOOT
        elif _internal_goal_on_view and not _internal_line_limit and _internal_ball_on_view and abs(error_ball) < 20:
            v, w = self._pid(1, 0.05, 0.0, error)
            self._send_speed(v, w)
        elif self._has_ball() and _internal_goal_on_view and not _internal_line_limit:
            v, w = self._pid(1, 0.05, 0.0, error)
            self._send_speed(v, w)
        
        elif self._has_ball() and not _internal_goal_on_view:
            self.state = State.FRAME_SEARCH
        elif not self._has_ball() and not _internal_ball_on_view:
            self.state = State.BALL_SEARCH
        elif _internal_ball_on_view and not self._has_ball():
            self.state = State.BALL_APPROACH

    def _state_shoot(self):
        logger.info("Shooting")
        self._send_speed(0.8, 0.0)
        sleep(0.1)
        self.tx_queue.put_nowait(Message.servo(100))
        sleep(0.05)
        self.tx_queue.put_nowait(Message.drive(-1, 0))
        sleep(0.3)
        with self.shared.lock:
            goal_on_view = self.shared.data["goal_on_view"]
            ball_on_view = self.shared.data["ball_on_view"]

        if goal_on_view and ball_on_view:
            self.running.clear()
            self.state = State.IDLE
            sleep(0.5)
            self.tx_queue.put_nowait(Message.servo(180))
        else:
            self._send_speed(-1, 0)
            sleep(2)
            self.state = State.BALL_SEARCH

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
        