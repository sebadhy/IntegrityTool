"""Container roles for the same application, without provisioning or auth setup."""
from __future__ import annotations

import argparse
import os
import sys

from .deployment_check import configuration_errors


def main():
    parser = argparse.ArgumentParser(description="Iniciar API local o trabajador con almacenamiento compartido.")
    parser.add_argument("role", choices=["api", "worker"])
    role = parser.parse_args().role
    errors = configuration_errors(role)
    if errors:
        raise SystemExit("\n".join(errors))
    if role == "worker":
        command = [sys.executable, "-m", "src.review_worker"]
    else:
        print("La API mantiene acceso HTTP local. Consulte docs/azure_deployment.md antes de exponerla.",
            file=sys.stderr, flush=True)
        command = [sys.executable, "-m", "uvicorn", "src.workbench_api:app",
            "--host", "127.0.0.1", "--port", "8000", "--workers", "1"]
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
