import yaml
import threading
from src.config import Config

class ConfigManager:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._config = None
        self._load()

    def _load(self):
        with open(self.path, "r") as f:
            raw = yaml.safe_load(f)
        self._config = Config(**raw)

    def get(self) -> Config:
        with self._lock:
            return Config(**self._config.model_dump())

    def update(self, updated_config):
        """
        updater_fn: function que recibe el config y lo modifica
        """
        with self._lock:
            validated = Config(**updated_config.model_dump())

            # Guardado seguro
            with open(self.path, "w") as f:
                yaml.dump(validated.model_dump(), f, sort_keys=False)

            self._config = validated
