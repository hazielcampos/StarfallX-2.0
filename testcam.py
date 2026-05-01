from picamera2 import Picamera2
import cv2
import numpy as np
from time import sleep
import os

# =========================
# Archivo de configuración
# =========================
CONFIG_FILE = "hsv_config.txt"

# valores por defecto
params = {
    "h_min": 5, "h_max": 25,
    "s_min": 80, "s_max": 255,
    "b_min": 140, "b_max": 200
}

# cargar si existe
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        for line in f:
            k, v = line.strip().split("=")
            params[k] = int(v)

# =========================
# Cámara
# =========================
picam2 = Picamera2()

config = picam2.create_video_configuration(
    main={"size": (960, 540)},
    sensor={"output_size": (2304, 1296)}
)

picam2.configure(config)
picam2.start()

# =========================
# Ventana y sliders
# =========================
cv2.namedWindow("Controls")

def nothing(x):
    pass

cv2.createTrackbar("H min", "Controls", params["h_min"], 179, nothing)
cv2.createTrackbar("H max", "Controls", params["h_max"], 179, nothing)
cv2.createTrackbar("S min", "Controls", params["s_min"], 255, nothing)
cv2.createTrackbar("S max", "Controls", params["s_max"], 255, nothing)
cv2.createTrackbar("B min", "Controls", params["b_min"], 255, nothing)
cv2.createTrackbar("B max", "Controls", params["b_max"], 255, nothing)

# =========================
# Loop principal
# =========================
while True:
    frame = picam2.capture_array()
    frame = cv2.rotate(frame, cv2.ROTATE_180)

    frame_blur = cv2.GaussianBlur(frame, (3, 3), 0)

    hsv = cv2.cvtColor(frame_blur, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(frame_blur, cv2.COLOR_BGR2LAB)

    h = hsv[:, :, 0]
    s = hsv[:, :, 1]
    b = lab[:, :, 2]

    # leer sliders
    h_min = cv2.getTrackbarPos("H min", "Controls")
    h_max = cv2.getTrackbarPos("H max", "Controls")
    s_min = cv2.getTrackbarPos("S min", "Controls")
    s_max = cv2.getTrackbarPos("S max", "Controls")
    b_min = cv2.getTrackbarPos("B min", "Controls")
    b_max = cv2.getTrackbarPos("B max", "Controls")

    # máscaras
    mask1 = cv2.inRange(h, h_min, h_max)
    mask2 = cv2.inRange(s, s_min, s_max)
    mask3 = cv2.inRange(b, b_min, b_max)

    mask = cv2.bitwise_and(mask1, mask2)
    mask = cv2.bitwise_and(mask, mask3)

    # limpieza
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    cv2.imshow("Frame", frame)
    cv2.imshow("Mask", mask)

    key = cv2.waitKey(1) & 0xFF

    # guardar configuración
    if key == ord('s'):
        with open(CONFIG_FILE, "w") as f:
            f.write(f"h_min={h_min}\n")
            f.write(f"h_max={h_max}\n")
            f.write(f"s_min={s_min}\n")
            f.write(f"s_max={s_max}\n")
            f.write(f"b_min={b_min}\n")
            f.write(f"b_max={b_max}\n")
        print("Configuración guardada 🔥")

    if key == ord('q'):
        break

    sleep(0.02)

cv2.destroyAllWindows()
