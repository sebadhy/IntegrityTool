"""Start the API or background worker using shared storage configuration."""
from __future__ import annotations

import argparse
import os
import sys

from .deployment_check import configuration_errors


def main():
    parser = argparse.ArgumentParser(description="Iniciar API institucional o trabajador con almacenamiento compartido.")
    parser.add_argument("role", choices=["api", "worker"])
    role = parser.parse_args().role
    errors = configuration_errors(role)
    if errors:
        raise SystemExit("\n".join(errors))
    if role == "worker":
        command = [sys.executable, "-m", "src.review_worker"]
    else:
        command = [sys.executable, "-m", "uvicorn", "src.workbench_api:app",
            "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
