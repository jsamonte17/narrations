"""Small helpers for visible, timestamped progress in long-running stages."""

import threading
import time
from contextlib import contextmanager
from datetime import datetime


def report_progress(message):
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


@contextmanager
def progress_heartbeat(label, interval_seconds=15):
    stopped = threading.Event()
    started_at = time.monotonic()

    def report_elapsed():
        while not stopped.wait(interval_seconds):
            elapsed = int(time.monotonic() - started_at)
            report_progress(f"{label} is still running ({elapsed}s elapsed).")

    worker = threading.Thread(target=report_elapsed, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join()
