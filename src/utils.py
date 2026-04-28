from threading import Lock

class SharedData:
    def __init__(self):
        self.lock = Lock()

        self.data = {
            "possession": False,
            "ball_on_view": False,
            "ball_x": 0,
            "goal_on_view": False,
            "goal_x": 0,
            "ultrasonic_1": 0.0,
            "ultrasonic_2": 0.0,
            "ir_1": 0.0,
            "ir_2": 0.0
        }