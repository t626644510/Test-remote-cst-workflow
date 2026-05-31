"""CST stability diagnostic — deterministic replay test with system profiling.

Usage::

    python examples/diagnose_cst_stability.py --n 10
    python examples/diagnose_cst_stability.py --n 10 --skip-wakefield
    python examples/diagnose_cst_stability.py --n 5 --wakefield-only --npz D:/Results/raw_curves/eval_0005_f2f.npz --params 57.15,49.20,-72.03,88.63,4.91,21.71,17.88,1.49,5.76,23.50,26.86,9.82,8.31,-6.51

Repeats the F2F → inter-pass-reset → F2W cycle N times with fixed
parameters to measure CST stability.  Collects system profiles so you
can diff two machines.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime

# Ensure src/ is on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_project_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

import numpy as np
import yaml


# ---------------------------------------------------------------------------
# System profile collection
# ---------------------------------------------------------------------------

def collect_system_profile(output_dir: str, library_path: str = "") -> str:
    """Gather Windows / hardware / Python / CST info and save as JSON."""
    profile: dict = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # -- Windows --
    profile["windows"] = {
        "version": platform.version(),
        "release": platform.release(),
        "build": platform.win32_ver()[1] if hasattr(platform, "win32_ver") else "",
        "machine": platform.machine(),
        "processor": platform.processor(),
    }

    # -- Hardware (via wmic) --
    try:
        cpu_out = subprocess.check_output(
            ["wmic", "cpu", "get", "Name,NumberOfCores,MaxClockSpeed", "/format:csv"],
            shell=True, timeout=10,
        ).decode("gbk", errors="replace")
        profile["cpu_raw"] = cpu_out.strip()
    except Exception:
        profile["cpu_raw"] = "N/A"

    try:
        mem_out = subprocess.check_output(
            ["wmic", "computersystem", "get", "TotalPhysicalMemory", "/format:csv"],
            shell=True, timeout=10,
        ).decode("gbk", errors="replace")
        profile["memory_raw"] = mem_out.strip()
    except Exception:
        profile["memory_raw"] = "N/A"

    # -- Python --
    profile["python"] = {
        "version": sys.version,
        "executable": sys.executable,
        "arch": platform.architecture()[0],
    }

    # -- CST (via COM) --
    if library_path:
        try:
            from cst_optimization.core.connection import CSTConnection
            from cst_optimization.core.cleanup import kill_all_cst_processes
            conn = CSTConnection(library_path=library_path, mode="any_or_new")
            conn.connect()
            try:
                profile["cst"] = {
                    "version": str(getattr(conn._de, "GetApplicationVersion", lambda: "N/A")()),
                }
            except Exception:
                profile["cst"] = {"version": "COM connected but version query failed"}
            finally:
                try:
                    conn.close(force=True)
                except Exception:
                    pass
                time.sleep(3)
                kill_all_cst_processes()
        except Exception as e:
            profile["cst"] = {"error": str(e)[:200]}
    else:
        profile["cst"] = {"error": "library_path not provided"}

    # -- CST project files --
    for proj_path in ["D:/workflow2/F2F.cst", "D:/workflow2/F2W.cst",
                       "D:/workflow2/F2W_offset.cst"]:
        label = os.path.basename(proj_path)
        if os.path.isfile(proj_path):
            st = os.stat(proj_path)
            profile[f"project_{label}"] = {
                "size_mb": round(st.st_size / 1e6, 2),
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
            }
        else:
            profile[f"project_{label}"] = "NOT FOUND"

    # -- Save --
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"system_profile_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    print(f"[profile] saved to {path}")
    return path


# ---------------------------------------------------------------------------
# Safe CST connection close (graceful first, force-kill fallback)
# ---------------------------------------------------------------------------

def _safe_close_connection(
    conn,
    cooldown_s: float = 5.0,
    graceful_timeout_s: float = 15.0,
) -> None:
    """Close a CST connection: graceful first, force-kill the PID if it hangs."""
    from cst_optimization.core.cleanup import (
        force_kill_cst, verify_process_cleanup, kill_all_cst_processes,
    )

    pid = getattr(conn, "pid", None)
    # Try graceful close with timeout
    hung = False
    try:
        import threading as _th
        closed = _th.Event()
        def _do_close():
            try:
                conn.close(force=False)
            except Exception:
                pass
            closed.set()
        t = _th.Thread(target=_do_close, daemon=True)
        t.start()
        t.join(graceful_timeout_s)
        if t.is_alive():
            hung = True
            print(f"  [WARNING] DesignEnvironment.close() hung (PID={pid}) — "
                  f"abandoning COM thread. Falling back to force-kill.")
    except Exception:
        hung = True

    if hung and pid is not None and pid > 0:
        try:
            force_kill_cst(pid)
            if verify_process_cleanup(pid, timeout_s=10.0):
                print(f"  Force-killed CST PID={pid} — confirmed dead")
            else:
                print(f"  Force-killed CST PID={pid} — still alive, "
                      f"falling back to kill_all_cst_processes")
                kill_all_cst_processes()
        except Exception as e:
            print(f"  Force-kill failed for PID={pid}: {e}")
    elif not hung and pid is not None and pid > 0:
        # Post-verification: conn.close() returned but process may still be alive
        # (e.g. force_kill_cst inside close() failed silently)
        if not verify_process_cleanup(pid, timeout_s=5.0):
            print(f"  [WARNING] conn.close() returned but PID={pid} still alive "
                  f"— force-killing")
            force_kill_cst(pid)
            if not verify_process_cleanup(pid, timeout_s=5.0):
                print(f"  [WARNING] PID={pid} still alive after force_kill "
                      f"— kill_all_cst_processes")
                kill_all_cst_processes()

    time.sleep(cooldown_s)


# ---------------------------------------------------------------------------
# Default test parameters (iter 0 LHS point from the failed run)
# ---------------------------------------------------------------------------

DEFAULT_PARAMS = [
    48.4188, 143.5606, -62.0674, 40.9698, 1.5694, 4.5499, 12.3823,
    14.9182, 18.4006, 9.4582, 21.1545, 13.0417, 23.6157, -14.4453,
]

PARAM_NAMES = [
    "selfangle1", "selfangle2", "inner_angle", "inner_angle3",
    "FolkHeight", "FolkHeight2", "UpperHeight1", "UpperHeight2",
    "DownHeight1", "DownHeight2", "Lin2", "inner_r2", "Lin", "inner_r",
]


# ---------------------------------------------------------------------------
# F2F + inter-pass-reset + F2W cycle test
# ---------------------------------------------------------------------------

def run_stability_test(
    n: int,
    params: list[float],
    skip_wakefield: bool = False,
    config_path: str = "config/default.yaml",
) -> dict:
    """Repeat the F2F→reset→F2W cycle N times and report statistics."""
    from cst_optimization.core.connection import CSTConnection
    from cst_optimization.core.project import CSTProject
    from cst_optimization.core.solver import SolverRunner
    from cst_optimization.core.messages import MessageLogger
    from cst_optimization.core.cleanup import (
        remove_result_folder, remove_lock_file,
    )

    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    wf2 = cfg.get("workflow_2", {})
    projects_cfg = wf2.get("projects", {})
    cst_cfg = cfg.get("cst", {})
    library_path = cst_cfg.get("library_path", r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries")
    cooldown_s = float(wf2.get("optimization", {}).get("retry", {}).get("cooldown_s", 15.0))

    param_dict = dict(zip(PARAM_NAMES, params))

    results: list[dict] = []
    times_f2f: list[float] = []
    times_f2w: list[float] = []
    failures_f2f: list[str] = []
    failures_f2w: list[str] = []

    solver = SolverRunner(timeout_s=300.0, settle_s=2.0)
    msg = MessageLogger(output_dir="D:/Results/cst_messages", enabled=True)

    for i in range(n):
        print(f"\n{'='*60}")
        print(f"Cycle {i+1}/{n}")
        print(f"{'='*60}")
        result = {"cycle": i + 1, "f2f": "FAIL", "f2w": "N/A"}

        # ── Phase 1: F2F ──────────────────────────────────────────
        f2f_path = projects_cfg["frequency_domain"]["cst_path"]
        conn = CSTConnection(library_path=library_path, mode="new")
        f2f_ok = False
        try:
            conn.connect()
            conn.set_quiet_mode(True)
            print(f"  DE PID={conn.pid}")

            proj = conn.open_project(f2f_path)
            proj.update_parameters(param_dict, use_full_rebuild=True)
            msg.capture(proj)
            msg.clear()
            t0 = time.perf_counter()
            solver_result = solver.run(proj)
            elapsed = time.perf_counter() - t0
            msg.capture(proj)
            msg.write(label="frequency_domain", iteration=i)

            if solver_result.success:
                times_f2f.append(elapsed)
                result["f2f"] = "OK"
                result["f2f_elapsed"] = round(elapsed, 1)
                result["f2f_cells"] = solver_result.mesh_cells or "?"
                proj.save()
                print(f"  F2F OK ({elapsed:.0f}s, {solver_result.mesh_cells or '?'} cells)")
                f2f_ok = True
            else:
                failures_f2f.append(solver_result.error_type or "unknown")
                result["f2f"] = f"FAIL[{solver_result.error_type}]"
                result["f2f_elapsed"] = round(elapsed, 1)
                print(f"  F2F FAIL [{solver_result.error_type}] ({elapsed:.0f}s)")
                results.append(result)
        except Exception as e:
            failures_f2f.append(f"exception:{type(e).__name__}")
            result["f2f"] = f"EXC:{type(e).__name__}"
            print(f"  F2F EXCEPTION: {e}")
            results.append(result)
        finally:
            # Always close the F2F connection, even on failure/exception
            _safe_close_connection(conn, cooldown_s=cooldown_s)

        if not f2f_ok:
            continue

        # ── Inter-pass cleanup ─────────────────────────────────────
        # F2F connection is already closed by the finally block above.
        # Clean conditional-project result folders only (keep F2F).
        print(f"  Inter-pass cleanup (cooldown={cooldown_s}s)...")
        # Clean conditional-project result folders only (keep F2F)
        for spec_label, spec_cfg in projects_cfg.items():
            if spec_label == "frequency_domain":
                continue
            try:
                remove_result_folder(spec_cfg["cst_path"])
            except Exception:
                pass
            try:
                remove_lock_file(os.path.splitext(spec_cfg["cst_path"])[0])
            except Exception:
                pass
        time.sleep(cooldown_s)

        if skip_wakefield:
            result["f2w"] = "SKIP"
            results.append(result)
            continue

        # ── Phase 1.5: F2W ────────────────────────────────────────
        f2w_path = projects_cfg["wakefield"]["cst_path"]
        conn2 = CSTConnection(library_path=library_path, mode="new")
        try:
            conn2.connect()
            conn2.set_quiet_mode(True)
            print(f"  New DE PID={conn2.pid}")

            proj2 = conn2.open_project(f2w_path)
            proj2.update_parameters(param_dict, use_full_rebuild=True)
            msg.capture(proj2)
            msg.clear()
            t0 = time.perf_counter()
            solver_result2 = solver.run(proj2)
            elapsed2 = time.perf_counter() - t0
            msg.capture(proj2)
            msg.write(label="wakefield", iteration=i)

            if solver_result2.success:
                times_f2w.append(elapsed2)
                result["f2w"] = "OK"
                result["f2w_elapsed"] = round(elapsed2, 1)
                print(f"  F2W OK ({elapsed2:.0f}s)")
                proj2.save()
            else:
                failures_f2w.append(solver_result2.error_type or "unknown")
                result["f2w"] = f"FAIL[{solver_result2.error_type}]"
                result["f2w_elapsed"] = round(elapsed2, 1)
                print(f"  F2W FAIL [{solver_result2.error_type}] ({elapsed2:.0f}s)")
        except Exception as e:
            failures_f2w.append(f"exception:{type(e).__name__}")
            result["f2w"] = f"EXC:{type(e).__name__}"
            print(f"  F2W EXCEPTION: {e}")
        finally:
            _safe_close_connection(conn2, cooldown_s=2)

        # ── Cleanup (conn is already dead from inter-pass reset) ──
        results.append(result)

    # ── Summary statistics ────────────────────────────────────────────
    f2f_ok = sum(1 for r in results if r["f2f"] == "OK")
    f2w_ok = sum(1 for r in results if r["f2w"] == "OK")
    f2w_total = sum(1 for r in results if r["f2w"] != "SKIP")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Cycles: {n}")
    print(f"F2F: {f2f_ok}/{n} OK ({100*f2f_ok/n:.0f}%)")
    if times_f2f:
        print(f"     mean={np.mean(times_f2f):.0f}s  min={np.min(times_f2f):.0f}s  max={np.max(times_f2f):.0f}s")
    if failures_f2f:
        print(f"     failures: {dict(Counter(failures_f2f))}")

    if not skip_wakefield:
        print(f"F2W: {f2w_ok}/{f2w_total} OK ({100*f2w_ok/max(f2w_total,1):.0f}%)")
        if times_f2w:
            print(f"     mean={np.mean(times_f2w):.0f}s  min={np.min(times_f2w):.0f}s  max={np.max(times_f2w):.0f}s")
        if failures_f2w:
            print(f"     failures: {dict(Counter(failures_f2w))}")

    return {
        "n": n, "f2f_ok": f2f_ok, "f2w_ok": f2w_ok,
        "times_f2f": times_f2f, "times_f2w": times_f2w,
        "failures_f2f": Counter(failures_f2f),
        "failures_f2w": Counter(failures_f2w),
        "results": results,
    }


# ---------------------------------------------------------------------------
# F2W-only test (skip F2F, go directly to F2W)
# ---------------------------------------------------------------------------

def run_wakefield_only_test(
    n: int,
    params: list[float],
    npz_path: str,
    config_path: str = "config/default.yaml",
) -> dict:
    """Test F2W solver N times with fixed params, replaying F2F from .npz."""
    from cst_optimization.core.connection import CSTConnection
    from cst_optimization.core.solver import SolverRunner
    from cst_optimization.core.messages import MessageLogger
    from cst_optimization.database import VirtualResultReader

    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    wf2 = cfg.get("workflow_2", {})
    projects_cfg = wf2.get("projects", {})
    cst_cfg = cfg.get("cst", {})
    library_path = cst_cfg.get("library_path", r"D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries")
    cooldown_s = float(wf2.get("optimization", {}).get("retry", {}).get("cooldown_s", 15.0))
    pre_filter_db = float(wf2.get("pre_filter", {}).get("absorption_threshold_db", -25.0))

    param_dict = dict(zip(PARAM_NAMES, params))
    f2w_path = projects_cfg["wakefield"]["cst_path"]

    # Verify F2F .npz
    if not os.path.isfile(npz_path):
        print(f"ERROR: .npz not found: {npz_path}")
        return {"error": "npz_not_found"}

    vreader = VirtualResultReader(npz_path)
    # Quick absorption check
    try:
        sd = vreader.get_s_parameter(r"1D Results\S-Parameters\S2,1")
        s_db = float(20.0 * np.log10(np.max(np.abs(sd.s_complex))))
        print(f"[.npz] antenna_absorption = {s_db:.2f} dB (threshold: {pre_filter_db} dB)")
    except Exception as e:
        print(f"WARNING: cannot read S-parameters from .npz: {e}")

    solver = SolverRunner(timeout_s=300.0, settle_s=2.0)
    msg = MessageLogger(output_dir="D:/Results/cst_messages", enabled=True)

    results: list[dict] = []
    times: list[float] = []
    failures: list[str] = []

    for i in range(n):
        print(f"\n{'='*60}")
        print(f"F2W-only Cycle {i+1}/{n}")
        print(f"{'='*60}")
        result = {"cycle": i + 1}

        conn = CSTConnection(library_path=library_path, mode="new")
        try:
            conn.connect()
            conn.set_quiet_mode(True)
            print(f"  DE PID={conn.pid}")

            proj = conn.open_project(f2w_path)
            proj.update_parameters(param_dict, use_full_rebuild=True)
            msg.capture(proj)
            msg.clear()
            t0 = time.perf_counter()
            solver_result = solver.run(proj)
            elapsed = time.perf_counter() - t0
            msg.capture(proj)
            msg.write(label="wakefield", iteration=i)

            if solver_result.success:
                times.append(elapsed)
                result["status"] = "OK"
                result["elapsed"] = round(elapsed, 1)
                print(f"  OK ({elapsed:.0f}s, {solver_result.mesh_cells or '?'} cells)")
                proj.save()
            else:
                failures.append(solver_result.error_type or "unknown")
                result["status"] = f"FAIL[{solver_result.error_type}]"
                result["elapsed"] = round(elapsed, 1)
                print(f"  FAIL [{solver_result.error_type}] ({elapsed:.0f}s)")
        except Exception as e:
            failures.append(f"exception:{type(e).__name__}")
            result["status"] = f"EXC:{type(e).__name__}"
            print(f"  EXCEPTION: {e}")
        finally:
            _safe_close_connection(conn, cooldown_s=2)

        results.append(result)

    ok = sum(1 for r in results if r.get("status") == "OK")
    print(f"\nF2W-only: {ok}/{n} OK ({100*ok/max(n,1):.0f}%)")
    if times:
        print(f"  mean={np.mean(times):.0f}s  min={np.min(times):.0f}s  max={np.max(times):.0f}s")
    if failures:
        print(f"  failures: {dict(Counter(failures))}")

    return {"n": n, "ok": ok, "times": times, "failures": Counter(failures), "results": results}


# ---------------------------------------------------------------------------
# COM connection health check
# ---------------------------------------------------------------------------

def com_health_check(library_path: str) -> bool:
    """Rapid COM health check — connect, ping, disconnect."""
    from cst_optimization.core.connection import CSTConnection
    print("COM health check...")
    try:
        conn = CSTConnection(library_path=library_path, mode="any_or_new")
        conn.connect()
        print(f"  Connected: PID={conn.pid}")
        time.sleep(1)
        _safe_close_connection(conn, cooldown_s=2, graceful_timeout_s=25)
        # Verify no orphan CST processes remain
        from cst_optimization.core.cleanup import kill_all_cst_processes
        leftover = kill_all_cst_processes()
        if leftover > 0:
            print(f"  Closed (killed {leftover} leftover CST process(es))")
        else:
            print("  Closed (no leftover processes)")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CST Stability Diagnostic — deterministic replay test"
    )
    parser.add_argument("--n", type=int, default=10, help="Number of cycles")
    parser.add_argument("--config", type=str, default="config/default.yaml")
    parser.add_argument("--skip-wakefield", action="store_true",
                        help="Only test F2F loop (no wakefield solver)")
    parser.add_argument("--wakefield-only", action="store_true",
                        help="Only test F2W solver (skip F2F, requires --npz)")
    parser.add_argument("--npz", type=str, default="",
                        help="Path to F2F .npz for --wakefield-only mode")
    parser.add_argument("--params", type=str, default="",
                        help="Comma-separated parameter values (14 numbers)")
    parser.add_argument("--profile-only", action="store_true",
                        help="Only collect system profile, no solver test")
    parser.add_argument("--health-only", action="store_true",
                        help="Only run COM health check")
    args = parser.parse_args()

    output_dir = "D:/Results"

    # ── Load config first (needed for library_path) ────────────────
    with open(args.config, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    library_path = cfg.get("cst", {}).get("library_path", "")

    # ── System profile (always collected) ──────────────────────────
    profile_path = collect_system_profile(output_dir, library_path=library_path)

    # ── COM health check ───────────────────────────────────────────

    if args.health_only:
        com_health_check(library_path)
        return

    if args.profile_only:
        return

    # ── Parse params ───────────────────────────────────────────────
    params = DEFAULT_PARAMS
    if args.params:
        params = [float(x.strip()) for x in args.params.split(",")]
        if len(params) != 14:
            print(f"ERROR: expected 14 parameters, got {len(params)}")
            sys.exit(1)

    print(f"Test parameters: {dict(zip(PARAM_NAMES, params))}")
    print(f"Config: {args.config}")
    print(f"Profile: {profile_path}")

    # ── COM health check before starting ───────────────────────────
    if not com_health_check(library_path):
        print("WARNING: COM health check failed — continuing anyway...")

    # ── Run test ───────────────────────────────────────────────────
    if args.wakefield_only:
        if not args.npz:
            print("ERROR: --wakefield-only requires --npz <path to F2F .npz>")
            sys.exit(1)
        run_wakefield_only_test(args.n, params, args.npz, args.config)
    else:
        run_stability_test(args.n, params, args.skip_wakefield, args.config)

    print(f"\nSystem profile: {profile_path}")


if __name__ == "__main__":
    main()
