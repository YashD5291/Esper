"""PyInstaller entry point for esper-server.

Thin wrapper that imports from the src package (preserving relative imports)
and calls main().
"""
from src.server import main

if __name__ == "__main__":
    main()
