"""
run_api.py
Launcher script for SMTE FastAPI REST API backend.
Runs Uvicorn on http://0.0.0.0:8000 with auto-reload.
"""

import sys
import os
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import uvicorn

if __name__ == "__main__":
    print("=" * 65)
    print("  SMTE INSTITUTIONAL REST API SERVER")
    print("  Version: 2.0.0")
    print("  Docs:    http://127.0.0.1:8000/docs")
    print("  Health:  http://127.0.0.1:8000/health")
    print("=" * 65)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
