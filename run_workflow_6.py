"""WF6 compatibility entry point; only on its canonical workflow branch."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent / "src"))
from workflows.rfgun_wake_thermal.run import main
if __name__ == "__main__":
    raise SystemExit(main())
