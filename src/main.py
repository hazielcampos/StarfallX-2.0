from queue import Queue
from threading import Thread, Event
from src.handlers import CommsHandler, ControlHandler, VisionHandler, StreamsHandler
from src.shared import SharedData
from time import sleep
import logging
from src.handlers.comms import Message
import os
import lgpio
from src.config import ConfigManager
from src.utils import cli_interface

h = lgpio.gpiochip_open(0)

logging.basicConfig(
    level=logging.INFO,          # DEBUG para ver todo, INFO para solo eventos importantes
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')

stop_event = Event()
running_event = Event()

shared = SharedData()
config_manager = ConfigManager(CONFIG_PATH)
rx_queue = Queue(maxsize=300)
tx_queue = Queue(maxsize=300)

comms = CommsHandler(shared, rx_queue, tx_queue, "/dev/serial0", 115500, stop_event)
vision = VisionHandler(shared, config_manager, stop_event)
streams = StreamsHandler(shared, config_manager, stop_event)

control = ControlHandler(shared, rx_queue, tx_queue, stop_event, running_event)

comms_thread = Thread(target=comms.run, daemon=True).start()
vision_thread = Thread(target=vision.run, daemon=True).start()
streams_thread = Thread(target=streams.run, daemon=True).start()
control_thread = Thread(target=control.run, daemon=True).start()

cli_thread = Thread(target=cli_interface, args=(tx_queue, running_event, stop_event), daemon=True)
cli_thread.start()

PIN_START = 17
PIN_STOP = 27

# Configurar pines como entrada con pull-up
lgpio.gpio_claim_input(h, PIN_START, lgpio.SET_PULL_UP)
lgpio.gpio_claim_input(h, PIN_STOP, lgpio.SET_PULL_UP)

try:
    while True:
        start_state = lgpio.gpio_read(h, PIN_START)
        stop_state = lgpio.gpio_read(h, PIN_STOP)

        if start_state == 0 and not running_event.is_set():
            logger.info("Robot started")
            running_event.set()
        elif stop_state == 0 and running_event.is_set():
            running_event.clear()
            logger.info("Robot stoped")
        sleep(0.05)
    
except KeyboardInterrupt:
    print("Finishing program...")
finally:
    running_event.clear()
    stop_event.set()