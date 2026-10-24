"""Load existing backend fixtures only for explicitly requested tool tests."""

import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = TOOL_ROOT.parents[1] / "src/api"
sys.path[:0] = [str(TOOL_ROOT), str(API_ROOT)]

pytest_plugins = ["tests.conftest"]
