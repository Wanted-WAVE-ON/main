from pathlib import Path

import uvicorn

SRC = Path(__file__).resolve().parent / "backend" / "src"

if __name__ == "__main__":
    uvicorn.run(
        "silent_orchestra.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        app_dir=str(SRC),
    )
