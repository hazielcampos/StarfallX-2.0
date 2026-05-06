from threading import Lock
from pydantic import BaseModel
from enum import Enum



class Data(Enum):
    LINE_LIMIT = 0

    BALL_ON_VIEW = 1
    BALL_ON_BOTTOM = 2
    BALL_X = 3
    BALL_Y = 4
    BALL_SIZE = 5
    
    GOAL_ON_VIEW = 6
    GOAL_X = 7

    ULTRASONIC_1 = 8
    ULTRASONIC_2 = 9
    IR_1 = 10
    IR_2 = 11


class SharedData:
    def __init__(self):
        self.lock = Lock()
        self.frames = {}

        self.data = {
            Data.LINE_LIMIT: False,

            Data.BALL_ON_VIEW: False,
            Data.BALL_ON_BOTTOM: False,
            Data.BALL_X: 0,
            Data.BALL_Y: 0,
            Data.BALL_SIZE: 0,

            Data.GOAL_ON_VIEW: False,
            Data.GOAL_X: 0,

            Data.ULTRASONIC_1: 0.0,
            Data.ULTRASONIC_2: 0.0,
            Data.IR_1: 0.0,
            Data.IR_2: 0.0,
        }
    
    def get(self, key: Data):
        with self.lock:
            return self.data[key]
    
    def update(self, key: Data, value):
        with self.lock:
            self.data[key] = value