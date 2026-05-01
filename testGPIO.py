import lgpio
from time import sleep
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%H:%M:%S",
)

# Abrir el chip GPIO (0 normalmente en Raspberry Pi)
h = lgpio.gpiochip_open(0)

PIN_START = 17
PIN_STOP = 27

# Configurar pines como entrada con pull-up
lgpio.gpio_claim_input(h, PIN_START, lgpio.SET_PULL_UP)
lgpio.gpio_claim_input(h, PIN_STOP, lgpio.SET_PULL_UP)

try:
    while True:
        os.system("clear")
        start_state = lgpio.gpio_read(h, PIN_START)
        stop_state = lgpio.gpio_read(h, PIN_STOP)

        logging.info(f"START (BCM 17): {start_state} | STOP (BCM 27): {stop_state}")

        sleep(0.02)

except KeyboardInterrupt:
    print("Finishing program...")

finally:
    lgpio.gpiochip_close(h)
