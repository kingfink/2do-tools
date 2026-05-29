import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from _2do_mcp.cli import main  # noqa: E402

raise SystemExit(main(["serve"]))
