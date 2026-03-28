"""PyInstaller entry point for esper-server.

Supports two modes:
  - Server mode (default): runs the main JSON-line server
  - Worker mode (--whisper-worker): runs the Whisper inference subprocess,
    reading/writing pickled messages on stdin/stdout
"""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--whisper-worker" in sys.argv:
        from src.whisper_worker import run_pipe_worker
        run_pipe_worker()
    else:
        from src.server import main
        main()
