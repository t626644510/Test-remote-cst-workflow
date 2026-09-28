"""Compatibility entrypoint for the canonical WF5 branch."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from workflows.rfgun_hom_target.run import main

if __name__ == "__main__":
    raise SystemExit(main())
