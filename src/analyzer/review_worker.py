"""A worker is a process of this application, not a separate analytical service."""
from __future__ import annotations

import logging
import threading
import uuid

from .review_store import JobLeaseLost

LOGGER = logging.getLogger(__name__)


class ReviewWorker:
    def __init__(self, service, *, lease_seconds: int = 90, poll_seconds: float = .25):
        self.service = service
        self.owner = str(uuid.uuid4())
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, name="integrity-review", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()

    def run(self):
        while not self.stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                LOGGER.exception("Worker iteration failed; persisted work retained")
                worked = False
            if not worked:
                self.stop.wait(self.poll_seconds)

    def run_once(self) -> bool:
        store = self.service.store
        lease = store.claim_job(self.owner, self.lease_seconds)
        if lease is None:
            return False
        finished = threading.Event()
        def heartbeat():
            while not finished.wait(max(.25, self.lease_seconds / 3)):
                try:
                    if not store.heartbeat(lease, self.lease_seconds):
                        return
                except Exception:
                    LOGGER.exception("Worker heartbeat unavailable")
                    return
        keeper = threading.Thread(target=heartbeat, name="integrity-lease", daemon=True)
        keeper.start()
        try:
            with store.job_context(lease):
                self.service.run(lease.case_id)
                store.complete_job(lease)
        except JobLeaseLost:
            LOGGER.warning("Expired worker result rejected for job %s", lease.id)
        finally:
            finished.set()
            keeper.join()
        return True
