from queue import Queue
from threading import Thread, Event
from handlers import CommsHandler, ControlHandler, VisionHandler
from src.utils import SharedData
from time import sleep

stop_event = Event()
running_event = Event()

shared = SharedData()
rx_queue = Queue(maxsize=100)
tx_queue = Queue(maxsize=100)

comms = CommsHandler(shared, rx_queue, tx_queue, "/dev/serial10", 115500, stop_event)
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

finally:
    running_event.clear()
    stop_event.set()
    sleep(0.1)
