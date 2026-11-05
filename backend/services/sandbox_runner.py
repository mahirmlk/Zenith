"""Sandbox runner (update.md §11).

Execution of untrusted paper code is OFF by default
(`SANDBOX_ENABLED=false`) and requires a separately reviewed isolated
runner. When enabled, code runs via `docker run` with hard limits:
no network, read-only workspace, memory/CPU caps, non-root, timeout.
The API server itself never execs user code.
"""
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def sandbox_enabled() -> bool:
    return os.environ.get("SANDBOX_ENABLED", "false").lower() == "true"


def run_in_sandbox(paper_id: str = "", code: str = "", timeout_seconds: int = 120) -> dict:
    if not sandbox_enabled():
        return {
            "status": "not attempted",
            "reason": "SANDBOX_ENABLED=false — planning only (update.md §11).",
        }
    if not code:
        return {"status": "not attempted", "reason": "No code supplied."}
    # Disposable container: no network, read-only root, caps, non-root.
    cmd = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--memory", "1g", "--cpus", "1", "--user", "65534:65534",
        "--pids-limit", "64", "--cap-drop=ALL",
        "--security-opt", "no-new-privileges",
        "-i", "python:3.12-slim",
        "python", "-c", code,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
        return {
            "status": "passed" if proc.returncode == 0 else "failed",
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-2000:],
        }
    except FileNotFoundError:
        return {"status": "failed", "reason": "docker not available on worker"}
    except subprocess.TimeoutExpired:
        return {"status": "timed_out", "reason": f"exceeded {timeout_seconds}s"}
