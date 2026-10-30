"""Run durable analysis work independently from the web process."""
from __future__ import annotations

import argparse
import os
import signal
from pathlib import Path

from dotenv import load_dotenv


def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    parser = argparse.ArgumentParser(description="Ejecutar trabajos persistentes de Integrity Tool.")
    parser.add_argument("--once", action="store_true", help="Procesar un trabajo disponible y terminar.")
    args = parser.parse_args()
    from .analyzer.storage_settings import create_review_store
    from .analyzer.workbench_service import WorkbenchService
    from .analyzer.review_worker import ReviewWorker
    store = create_review_store(root)
    service = WorkbenchService(root, None, store=store, embedded_worker=False,
        assisted=os.getenv("INTEGRITY_ASSISTED_ENABLED", "true").lower() == "true")
    worker = ReviewWorker(service)
    try:
        if args.once:
            worker.run_once()
        else:
            signal.signal(signal.SIGINT, lambda *_: worker.stop.set())
            signal.signal(signal.SIGTERM, lambda *_: worker.stop.set())
            worker.run()
    finally:
        service.close()


if __name__ == "__main__":
    main()
