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
    GOAL_SIZE = 8

    ULTRASONIC_1 = 9
    ULTRASONIC_2 = 10
    IR_1 = 11
    IR_2 = 12


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
            Data.GOAL_SIZE: 0,

            Data.ULTRASONIC_1: 0.0,
            Data.ULTRASONIC_2: 0.0,
            Data.IR_1: 0.0,
            Data.IR_2: 0.0,
        }
    def get_frame(self, stream_id: int):
        with self.lock:
            return self.frames.get(stream_id, None)
    def update_frame(self, stream_id: int, frame):
        with self.lock:
            self.frames[stream_id] = frame
    
    def get(self, *key: Data):
        with self.lock:
            if len(key) == 1:
                return self.data[key[0]]
            else:
                return tuple(self.data[k] for k in key)
    
    def update(self, key: Data, value):
        with self.lock:
            self.data[key] = value