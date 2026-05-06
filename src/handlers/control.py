from queue import Queue, Empty
from time import sleep, time
from src.shared import SharedData
from threading import Event
from src.classes.Messages import *
from enum import Enum
import random
import logging

# Logger
logger = logging.getLogger(__name__)

# Constants
BALL_SEARCH_ROTATION_SPEED = 0.7
GOAL_SEARCH_ROTATION_SPEED = 0.5

# FSM
class State(Enum):
    IDLE = 0
    BALL_SEARCH   = 1
    BALL_APPROACH  = 2 
    FRAME_SEARCH   = 3
    FRAME_APPROACH  = 4
    SHOOT  = 5
    AVOID_OBSTACLE = 6

class ControlHandler:
    def __init__(
        self,
        shared: SharedData,
        rx_queue: Queue,
        tx_queue: Queue,
        stop_event: Event,
        running: Event,
    ):
        # COMMS Queues and shared data
        self.rx_queue   = rx_queue
        self.tx_queue   = tx_queue
        self.shared     = shared

        # Events
        self.stop_event = stop_event
        self.running    = running

        # PID Variables
        self._prev_error = 0
        self._integral = 0

        # FSM
        self.state = State.IDLE
        
        # State: BALL_SEARCH Utility
        self._state_ball_search_last_switch_time = 0
        self._state_ball_search_last_direction = random.choice([-BALL_SEARCH_ROTATION_SPEED, BALL_SEARCH_ROTATION_SPEED])

        # State: GOAL_SEARCH Utility
        self._state_goal_approach_last_switch_time = 0
        self._state_goal_approach_last_direction = random.choice([-GOAL_SEARCH_ROTATION_SPEED, GOAL_SEARCH_ROTATION_SPEED])
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
        self._send_speed(0.0, 0.0)
        self.tx_queue.put_nowait(Message.servo(180))
        

    def _state_search_ball(self):
        pass

    def _state_approach_ball(self):
        pass

    def _state_frame_search(self):
        pass
    
    def _state_frame_approach(self):
        pass

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
        