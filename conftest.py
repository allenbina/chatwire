"""Root conftest.py — makes the flat-layout source tree importable from tests.

The repo uses a flat layout: source modules live at the project root rather
than under a `chatwire/` package directory. pytest's rootdir detection finds
this file and inserts the project root into sys.path before collecting any
tests, so `import prefix`, `from web.themes import …`, etc. all resolve
without requiring an editable install.
"""
import sys
from pathlib import Path

# Insert project root so tests can import top-level modules directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
