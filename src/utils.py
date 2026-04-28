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
            "ul_r": False,
            "ul_l": False
        }