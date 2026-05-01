from src.utils import SharedData
from time import sleep
from threading import Event
import logging
from queue import Queue
import numpy as np
from picamera2 import Picamera2
import cv2
logger = logging.getLogger(__name__)

lower_orange = np.array([5, 100, 100])
upper_orange = np.array([20, 255, 255])

class VisionHandler:
    def __init__(self, shared: SharedData, stop_event: Event):
        self.shared = shared
        self.stop_event = stop_event
        self.camera = Picamera2()
        self.config = self.camera.create_video_configuration(
            main={"size": (960, 540)},
            sensor={"output_size": (2304, 1296)}
        )
        self.camera.configure(self.config)
    
    def run(self):
        self.camera.set_controls({
            "AeEnable": False,
            "AwbEnable": False,

            # Exposición manual
            "ExposureTime": 10000,   # en microsegundos (prueba 5000–20000)
            "AnalogueGain": 25.0,     # ganancia (sube si está oscuro)

            # Balance de blancos manual
            "ColourGains": (2, 2)  # (R, B) — esto lo tienes que calibrar
        })
        self.camera.start()
        try:
            while not self.stop_event.is_set():
                frame = self.camera.capture_array()
                frame = cv2.rotate(frame, cv2.ROTATE_180)
                frame_blur = cv2.GaussianBlur(frame, (9, 9), 0)
                lab = cv2.cvtColor(frame_blur, cv2.COLOR_BGR2LAB)

                mask = cv2.inRange(lab, lower_orange, upper_orange)

                kernel = np.ones((5, 5), np.uint8)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                mask = cv2.dilate(mask, kernel, iterations=1)

                with self.shared.lock:
                    self.shared.frames[0x01] = frame_blur
                    self.shared.frames[0x02] = mask
                    self.shared.frames[0x03] = lab



                


                sleep(1/30)

        except KeyboardInterrupt:
            pass

        finally:
            self.camera.stop()
            cv2.destroyAllWindows()

        logger.info("Vision module finished.")