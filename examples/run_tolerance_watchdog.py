"""Launch tolerance_analysis.py under WatchdogRunner for crash-resilience.

The watchdog monitors the subprocess and restarts it on non-zero exit,
enabling checkpoint-based resume after CST crashes or transient failures.

Usage:
    .venv\\Scripts\\python examples\\run_tolerance_watchdog.py
    .venv\\Scripts\\python examples\\run_tolerance_watchdog.py --max-restarts 3 --cooldown 60
"""

import sys
import os as _os

_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_SRC_DIR = _os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import argparse
import yaml

from cst_optimization.watchdog import WatchdogConfig, WatchdogRunner

CONFIG_PATH = _os.path.join(_PROJECT_ROOT, "config", "default.yaml")


def main() -> None:
    cfg = yaml.safe_load(open(CONFIG_PATH, "r", encoding="utf-8"))
    wd_cfg = cfg.get("tolerance", {}).get("watchdog", {})
    if not wd_cfg.get("enabled", False):
        print("Watchdog is disabled in config (tolerance.watchdog.enabled=false).")
        print("Run tolerance_analysis.py directly, or set enabled: true in config.")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Run tolerance analysis under CST watchdog monitor")
    parser.add_argument("--max-restarts", type=int,
                        default=wd_cfg.get("max_restarts", 5),
                        help="Max automatic restarts (default from config)")
    parser.add_argument("--cooldown", type=float,
                        default=wd_cfg.get("cooldown_s", 30.0),
                        help="Cooldown seconds between restarts (default from config)")
    args = parser.parse_args()

    watch_cfg = WatchdogConfig(
        max_restarts=args.max_restarts,
        cooldown_s=args.cooldown,
    )
    runner = WatchdogRunner(watch_cfg)

    script = _os.path.join(_PROJECT_ROOT, "examples", "tolerance_analysis.py")
    cmd = [sys.executable, script]
    sys.exit(runner.run(cmd))


if __name__ == "__main__":
    main()
