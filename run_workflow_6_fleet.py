"""WF6 multi-station compatibility entry point."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from workflows.rfgun_wake_thermal.fleet.run import main
if __name__=='__main__':raise SystemExit(main())
