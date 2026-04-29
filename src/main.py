from queue import Queue
from threading import Thread, Event
from src.handlers import CommsHandler, ControlHandler, VisionHandler
from src.utils import SharedData
from time import sleep
import logging
from src.handlers.comms import Message

logging.basicConfig(
    level=logging.INFO,          # DEBUG para ver todo, INFO para solo eventos importantes
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

stop_event = Event()
running_event = Event()

shared = SharedData()
rx_queue = Queue(maxsize=100)
tx_queue = Queue(maxsize=100)

comms = CommsHandler(shared, rx_queue, tx_queue, "/dev/serial0", 115500, stop_event)
vision = VisionHandler(shared)
control = ControlHandler(shared, rx_queue, tx_queue, stop_event, running_event)

comms_thread = Thread(target=comms.run).start()
vision_thread = Thread(target=vision.run).start()
control_thread = Thread(target=control.run).start()

try:
    while True:
        sleep(0.1)
    
except KeyboardInterrupt:
    print("Finishing program...")
    tx_queue.put_nowait(Message.drive(0.0, 0.0))
    sleep(1)
finally:
    running_event.clear()
    stop_event.set()
    sleep(1)
