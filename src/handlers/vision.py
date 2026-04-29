from src.utils import SharedData
from time import sleep
from threading import Event
import logging
logger = logging.getLogger(__name__)

class VisionHandler:
    def __init__(self, shared: SharedData, stop_event: Event):
        self.shared = shared
        self.stop_event = stop_event
    
    def run(self):
        while not self.stop_event.is_set():
            sleep(0.1)

        logger.info("Vision module finished.")