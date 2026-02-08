import time
import os
import logging
from ..tasks import start_ingestion

logger = logging.getLogger(__name__)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class NewFileHandler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory and not event.src_path.endswith('.tmp'):
                logger.info(f"New file detected: {event.src_path}")
                # Trigger ingestion task
                start_ingestion.delay(event.src_path)

    def start_watcher(path_to_watch: str):
        if not os.path.exists(path_to_watch):
            logger.error(f"Watch directory does not exist: {path_to_watch}")
            return

        logger.info(f"Starting watcher on {path_to_watch}")
        event_handler = NewFileHandler()
        observer = Observer()
        observer.schedule(event_handler, path_to_watch, recursive=False)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

except ImportError:
    def start_watcher(path_to_watch: str):
        logger.error("Watchdog library not installed. Cannot start file watcher.")
        # Fallback to simple polling?
        logger.info("Falling back to simple polling...")
        seen_files = set()
        if os.path.exists(path_to_watch):
             seen_files = set(os.listdir(path_to_watch))

        while True:
            time.sleep(5)
            if not os.path.exists(path_to_watch):
                continue

            current_files = set(os.listdir(path_to_watch))
            new_files = current_files - seen_files

            for f in new_files:
                full_path = os.path.join(path_to_watch, f)
                if os.path.isfile(full_path) and not f.endswith('.tmp'):
                    logger.info(f"New file detected (polling): {full_path}")
                    start_ingestion.delay(full_path)

            seen_files = current_files
