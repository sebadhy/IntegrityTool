"""Launch the built workbench locally on Windows, macOS or Linux."""
from pathlib import Path
import os

if __name__ == "__main__":
    import uvicorn

    os.chdir(Path(__file__).resolve().parent)

    if not (Path(__file__).parent / "frontend/dist/index.html").is_file():
        raise SystemExit("Primero construya la interfaz: cd frontend, pnpm install, pnpm build.")
    uvicorn.run("src.workbench_api:app", host="127.0.0.1", port=8000, workers=1)
