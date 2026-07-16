"""spark-submit-compatible entry point for the public CLI."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPO_ROOT))

from benchmark.reliability_reference.cli import main  # noqa: E402

raise SystemExit(main())
