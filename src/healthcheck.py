"""Container liveness checks; no credentials, model requests or Docker API."""
import argparse
import os
import time
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["api", "worker"])
    args = parser.parse_args()
    try:
        if args.role == "api":
            with urlopen("http://127.0.0.1:8000/readyz", timeout=5) as response:
                assert response.status == 200
        else:
            timestamp = float(Path(os.environ["INTEGRITY_WORKER_HEARTBEAT_PATH"]).read_text())
            assert 0 <= time.time() - timestamp < 120
    except Exception:
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
