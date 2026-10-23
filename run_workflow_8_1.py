"""WF8.1 TRK command-line entry point."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from workflows.trk_multipacting.cli import main
if __name__ == "__main__":
    main()
