import yaml
import threading
import logging
from src.config import Config
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


logger = logging.getLogger("ConfigManager")


from pathlib import Path

class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, manager):
        self.manager = manager

    def _is_target_file(self, event):
        return Path(event.src_path).resolve() == Path(self.manager.path).resolve()

    def on_modified(self, event):
        if self._is_target_file(event):
            self.manager._reload_from_disk()

    def on_created(self, event):
        if self._is_target_file(event):
            self.manager._reload_from_disk()


class ConfigManager:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._config = None

        self._load()

        # Watcher setup
        self._observer = Observer()
        self._handler = ConfigFileHandler(self)

        folder = str(self.path.parent) if hasattr(self.path, "parent") else "."
        self._observer.schedule(self._handler, folder, recursive=False)
        self._observer.start()

        logger.info(f"Watcher iniciado para config: {self.path}")

    def _load(self):
        with open(self.path, "r") as f:
            raw = yaml.safe_load(f)
        self._config = Config(**raw)
        logger.info("Config cargado inicial")

    def _reload_from_disk(self):
        with self._lock:
            try:
                with open(self.path, "r") as f:
                    raw = yaml.safe_load(f)

                new_config = Config(**raw)

                # Solo log si realmente cambió
                if new_config != self._config:
                    self._config = new_config
                    logger.info("Config actualizado automáticamente desde archivo")

            except Exception as e:
                logger.error(f"Error recargando config: {e}")

    def get(self) -> Config:
        with self._lock:
            return Config(**self._config.model_dump())

    def update(self, updated_config):
        with self._lock:
            validated = Config(**updated_config.model_dump())

            with open(self.path, "w") as f:
                yaml.dump(validated.model_dump(), f, sort_keys=False)

            self._config = validated
            logger.info("Config actualizado manualmente y guardado en disco")

    def stop(self):
        self._observer.stop()
        self._observer.join()
        logger.info("Watcher detenido")
