import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_models_can_be_imported_first():
    """A fresh interpreter importing models before anything else: no circular import."""
    result = subprocess.run(
        [sys.executable, "-c", "import core.trackers.models"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
