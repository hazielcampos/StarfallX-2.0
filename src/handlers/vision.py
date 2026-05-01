from src.shared import SharedData
from time import sleep
from threading import Event
import logging
import numpy as np
import cv2

# Importación condicional para que funcione sin Raspberry Pi
try:
    from picamera2 import Picamera2
    HAS_PICAMERA = True
except ImportError:
    HAS_PICAMERA = False

logger = logging.getLogger(__name__)


class VisionHandler:
    def __init__(self, shared: SharedData, stop_event: Event):
        self.shared = shared
        self.stop_event = stop_event

        if HAS_PICAMERA:
            self.camera = Picamera2()
            self.config = self.camera.create_video_configuration(
                main={"size": (960, 540)},
                sensor={"output_size": (2304, 1296)}
            )
            self.camera.configure(self.config)
        else:
            self.camera = None
            logger.warning("Picamera2 no disponible — usando cámara USB/webcam.")
            self._cap = cv2.VideoCapture(0)
    def _get_ball(self, lab):
        pass
    def run(self):
        if self.camera:
            self.camera.set_controls({
                "AeEnable": False,
                "AwbEnable": False,
                "ExposureTime": 10000,
                "AnalogueGain": 25.0,
                "ColourGains": (2, 2)
            })
            self.camera.start()

        try:
            while not self.stop_event.is_set():
                # --- captura ---
                if self.camera:
                    frame = self.camera.capture_array()
                else:
                    ret, frame = self._cap.read()
                    if not ret:
                        sleep(1 / 30)
                        continue

                frame = cv2.rotate(frame, cv2.ROTATE_180)
                frame_blur = cv2.GaussianBlur(frame, (9, 9), 0)
                lab = cv2.cvtColor(frame_blur, cv2.COLOR_BGR2LAB)

                with self.shared.lock:
                    lower, upper = self.shared.get_lab_bounds()
                roi_ball = lab[0:300, 0:960]
                lower_arr = np.array(lower, dtype=np.uint8)
                upper_arr = np.array(upper, dtype=np.uint8)

                mask_ball = cv2.inRange(roi_ball, lower_arr, upper_arr)

                kernel = np.ones((5, 5), np.uint8)
                mask_ball = cv2.morphologyEx(mask_ball, cv2.MORPH_OPEN, kernel)
                mask_ball = cv2.morphologyEx(mask_ball, cv2.MORPH_CLOSE, kernel)
                mask_ball = cv2.dilate(mask_ball, kernel, iterations=2)
                
                mask_ball_show = cv2.cvtColor(roi_ball, cv2.COLOR_LAB2RGB)
                mask_ball_show = cv2.line(mask_ball_show, (480, 0), (480, 540), (255, 0, 0), 2)

                contours, _ = cv2.findContours(mask_ball, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                if contours:
                    # Contorno más grande
                    largest_contour = max(contours, key=cv2.contourArea)

                    # Filtrar ruido (opcional pero recomendado)
                    if cv2.contourArea(largest_contour) > 500:  
                        with self.shared.lock:
                            self.shared.data["ball_on_view"] = True

                        # Calcular centro usando momentos
                        M = cv2.moments(largest_contour)
                        if M["m00"] != 0:
                            cx = int(M["m10"] / M["m00"])
                            cy = int(M["m01"] / M["m00"])

                            # Dibujar punto
                            cv2.circle(mask_ball_show, (cx, cy), 6, (0, 255, 0), -1)

                            # Dibujar label
                            cv2.putText(mask_ball_show, f"({cx},{cy})", (cx+10, cy-10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)

                            # Dibujar contorno (opcional)
                            cv2.drawContours(mask_ball_show, [largest_contour], -1, (0,255,0), 2)
                            width = 960
                            center_x = width // 2  # 480

                            error_x = ((cx - center_x) / center_x) * 100

                            # Limitar por seguridad (por si algo se sale)
                            error_x = max(-100, min(100, error_x))
                            error_x = int(error_x)
                            error_x = error_x * -1
                            with self.shared.lock:
                                self.shared.data["ball_x"] = error_x

                            cv2.putText(mask_ball_show, f"Error: {error_x}", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 2, (0,255,255), 2)
                    else:
                        with self.shared.lock:
                            self.shared.data["ball_on_view"] = False


                with self.shared.lock:
                    self.shared.frames[0x01] = frame_blur
                    self.shared.frames[0x02] = lab
                    self.shared.frames[0x04] = mask_ball_show
                    self.shared.frames[0x03] = mask_ball
                sleep(1 / 30)

        except KeyboardInterrupt:
            pass
        finally:
            if self.camera:
                self.camera.stop()
            else:
                self._cap.release()
            cv2.destroyAllWindows()

        logger.info("Vision module finished.")
