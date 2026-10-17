import os
import sys
import tempfile
from pathlib import Path

# Isolate tests from the real ./data directory (config reads DATA_DIR at import).
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="sbtest_")
os.environ["MASSIVE_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
