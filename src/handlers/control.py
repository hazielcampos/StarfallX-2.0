from queue import Queue, Empty
from time import sleep, time
from src.shared import SharedData, Data
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
    SHOOT_START = 5      # Inicia el movimiento
    SHOOT_RELEASE = 6    # Acciona el servo
    SHOOT_RECOVER = 7    # Retrocede y finaliza

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
        self.prev_state = self.state

        
        # State: BALL_SEARCH Utility
        self._state_ball_search_last_switch_time = 0
        self._state_ball_search_last_direction = random.choice([-BALL_SEARCH_ROTATION_SPEED, BALL_SEARCH_ROTATION_SPEED])
        self._ball_lose_count = 0

        self._last_ball_x = 0
        self._lost_ball_time = 0

        # State: GOAL_SEARCH Utility
        self._state_goal_approach_last_switch_time = 0
        self._state_goal_approach_last_direction = random.choice([-GOAL_SEARCH_ROTATION_SPEED, GOAL_SEARCH_ROTATION_SPEED])
        self.start_search_time = 0
        self._goal_lose_count = 0

        self._has_ball_lose_count = 0

        self._start_delay_after_shoot = 0
        self._shoot_timer = 0


    # -------------------- PERCEPTION METHODS --------------------
    def _has_ball(self) -> bool:
        ball_size, ball_on_bottom = self.shared.get(
            Data.BALL_SIZE, 
            Data.BALL_ON_BOTTOM
        )
        if ball_size > 500 and ball_on_bottom:
            return True
        return False
    
    # -------------------- HELPER METHODS --------------------
    def _update_state(self, new_state: State):
        if self.state != new_state:
            self.prev_state = self.state
            logger.info(f"State change: {self.state.name} -> {new_state.name}")
            self.state = new_state

    def _pid(self, kp, kd, ki, error):
        # 1. Normalizar error (-1 a 1)
        e = error / 100.0

        # 2. Derivada
        derivative = e - self._prev_error

        # 3. Integral (con anti-windup ajustado a los límites)
        self._integral += e
        self._integral = max(min(self._integral, 0.5), -0.5)

        # 4. Cálculo de salida angular (w)
        w = kp * e + kd * derivative + ki * self._integral
        # Saturar w: Máximo 0.6, nunca menos de -0.6
        w = max(min(w, 0.6), -0.6)

        # 5. Velocidad lineal (v) mejorada
        # Queremos que v oscile entre 0.2 y 0.6
        # Si el error es 0, velocidad máxima (0.6)
        # Si el error es 1, velocidad mínima (0.2)
        v = 0.6 - (abs(e) * 0.4) 
        
        # Saturar v: Que nunca baje de 0.2 y nunca supere 0.6
        v = max(min(v, 0.6), 0.2)

        # 6. Guardar estado
        self._prev_error = e

        return v, w
    
    def _send_speed(self, v: float, w: float):
        self.tx_queue.put_nowait(Message.drive(v, w))
    
    # -------------------- STATE METHODS --------------------

    def _state_idle(self):
        self._send_speed(0.0, 0.0)
        self.tx_queue.put_nowait(Message.servo(180))

        self._prev_error = 0
        self._integral = 0

        # FSM
        self.state = State.IDLE
        self.prev_state = self.state

        
        # State: BALL_SEARCH Utility
        self._state_ball_search_last_switch_time = 0
        self._state_ball_search_last_direction = random.choice([-BALL_SEARCH_ROTATION_SPEED, BALL_SEARCH_ROTATION_SPEED])
        self._ball_lose_count = 0

        self._last_ball_x = 0
        self._lost_ball_time = 0

        # State: GOAL_SEARCH Utility
        self._state_goal_approach_last_switch_time = 0
        self._state_goal_approach_last_direction = random.choice([-GOAL_SEARCH_ROTATION_SPEED, GOAL_SEARCH_ROTATION_SPEED])
        self.start_search_time = 0
        self._goal_lose_count = 0

        self._has_ball_lose_count = 0

        self._start_delay_after_shoot = 0
        self._shoot_timer = 0
        
    def _state_search_ball(self):
        self._ball_lose_count = 0
        ball_on_view = self.shared.get(Data.BALL_ON_VIEW)

        if not ball_on_view:
            # Si no hay bola, rotar en la última dirección conocida
            self._send_speed(0.0, self._state_ball_search_last_direction)

            # Cambiar dirección cada 5 segundos para evitar quedarse atascado
            if time() - self._state_ball_search_last_switch_time > 5:
                self._state_ball_search_last_direction *= -1
                self._state_ball_search_last_switch_time = time()
        else:
            # Si la bola aparece, avanzar hacia ella
            self._send_speed(0.5, 0.0)
            self._update_state(State.BALL_APPROACH)

    def _state_approach_ball(self):
        ball_on_view, ball_error = self.shared.get(
            Data.BALL_ON_VIEW,
            Data.BALL_X
        )

        if not ball_on_view:
            self._ball_lose_count += 1
            if self._ball_lose_count > 10:
                self._update_state(State.BALL_SEARCH)
            return
        
        v, w = self._pid(kp=0.8, kd=0.1, ki=0.05, error=ball_error)
        self._send_speed(v, w)

        if self._has_ball():
            self._update_state(State.FRAME_SEARCH)

    def _state_frame_search(self):
        self._goal_lose_count = 0
        goal_on_view = self.shared.get(Data.GOAL_ON_VIEW)

        if not self._has_ball():
            self._has_ball_lose_count += 1
            if self._has_ball_lose_count > 10:
                self._has_ball_lose_count = 0
                self._update_state(State.BALL_SEARCH)
                return

        if not goal_on_view:
            # Rotar para buscar el marco
            self._send_speed(0.0, self._state_goal_approach_last_direction)

            # Cambiar dirección cada 5 segundos para evitar quedarse atascado
            if time() - self._state_goal_approach_last_switch_time > 5:
                self._state_goal_approach_last_direction *= -1
                self._state_goal_approach_last_switch_time = time()
        else:
            self._update_state(State.FRAME_APPROACH)
    
    def _state_frame_approach(self):
        goal_on_view, goal_error, ultrasonic, limit = self.shared.get(
            Data.GOAL_ON_VIEW,
            Data.GOAL_X,
            Data.ULTRASONIC_1,
            Data.LINE_LIMIT
        )

        if not self._has_ball():
            self._has_ball_lose_count += 1
            if self._has_ball_lose_count > 10:
                self._has_ball_lose_count = 0
                self._update_state(State.BALL_SEARCH)
                return
        
        if not goal_on_view:
            self._goal_lose_count += 1
            if self._goal_lose_count > 10:
                self._goal_lose_count = 0
                self._update_state(State.FRAME_SEARCH)
                return

        # Si estamos muy cerca del marco o hay una línea límite, preparamos el disparo
        if (ultrasonic < 34 and abs(goal_error) < 10) or limit:
            self._update_state(State.SHOOT_START)
            return

        v, w = self._pid(kp=0.8, kd=0.1, ki=0.05, error=goal_error)
        self._send_speed(v, w)


    def _state_shoot(self):
        # Inicialización del temporizador si es la primera vez que entramos al estado
        if self._shoot_timer == 0:
            self._shoot_timer = time()
            self._send_speed(0.8, 0.0) # Avanza al inicio
            self._update_state(State.SHOOT_START)

        elapsed = time() - self._shoot_timer

        # FASE 1: Preparación (Ya la hicimos al entrar)
        if self.state == State.SHOOT_START and elapsed > 0.1:
            self.tx_queue.put_nowait(Message.servo(100))
            self._update_state(State.SHOOT_RELEASE)
        
        # FASE 2: Accionamiento
        elif self.state == State.SHOOT_RELEASE and elapsed > 0.15:
            self._send_speed(-1.0, 0.0) # Retrocede
            self._update_state(State.SHOOT_RECOVER)
            
        # FASE 3: Finalización
        elif self.state == State.SHOOT_RECOVER and elapsed > 0.45:
            # Decisión final
            self._shoot_timer = 0
            goal_on_view, ball_on_view = self.shared.get(Data.GOAL_ON_VIEW, Data.BALL_ON_VIEW)
            if goal_on_view and ball_on_view:
                self.running.clear()
                self._update_state(State.IDLE)
                self.tx_queue.put_nowait(Message.servo(180))
            else:
                self._send_speed(0, 0)
                self._update_state(State.BALL_SEARCH)

    #-------------------- MAIN LOOP --------------------
    def run(self):
        # Define actions for each state
        actions = {
            State.IDLE: self._state_idle,
            State.BALL_SEARCH: self._state_search_ball,
            State.BALL_APPROACH: self._state_approach_ball,
            State.FRAME_SEARCH: self._state_frame_search,
            State.FRAME_APPROACH: self._state_frame_approach,
            State.SHOOT_START: self._state_shoot,
            State.SHOOT_RELEASE: self._state_shoot,
            State.SHOOT_RECOVER: self._state_shoot
        }

        while not self.stop_event.is_set():
            if not self.running.is_set():
                self._update_state(State.IDLE)
            else:
                if self.state == State.IDLE:
                    self._update_state(State.BALL_SEARCH)
                
            actions[self.state]()
            sleep(0.05)   # Loop frequency control (20 Hz)
        
        logger.info("Control module finished.")
        