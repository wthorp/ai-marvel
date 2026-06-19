#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import resource
import shutil
import subprocess
import time
from pathlib import Path


def usage_snapshot() -> dict[str, float]:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    value = usage.ru_maxrss
    if value > 10_000_000:
        max_rss_mb = value / 1024 / 1024
    else:
        max_rss_mb = value / 1024
    return {
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
        "max_rss_mb": max_rss_mb,
    }


def diff_usage(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {
        "user_cpu_seconds": after["user_cpu_seconds"] - before["user_cpu_seconds"],
        "system_cpu_seconds": after["system_cpu_seconds"] - before["system_cpu_seconds"],
        "max_rss_mb": after["max_rss_mb"],
    }


def start_gpu_sampler(path: Path) -> subprocess.Popen[str] | None:
    if not shutil.which("nvidia-smi"):
        return None
    query = "timestamp,index,name,utilization.gpu,memory.used,power.draw"
    cmd = [
        "nvidia-smi",
        f"--query-gpu={query}",
        "--format=csv",
        "-l",
        "1",
        "-f",
        str(path),
    ]
    try:
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return None


def stop_process(proc: subprocess.Popen[str] | None) -> None:
    if not proc:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a command and write timing/resource metrics.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.cmd and args.cmd[0] == "--":
        args.cmd = args.cmd[1:]
    if not args.cmd:
        raise SystemExit("Command required after --")

    args.log_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.log_dir / f"{args.name}.metrics.json"
    gpu_path = args.log_dir / f"{args.name}.gpu.csv"
    stdout_path = args.log_dir / f"{args.name}.stdout.log"
    stderr_path = args.log_dir / f"{args.name}.stderr.log"

    gpu_proc = start_gpu_sampler(gpu_path)
    before = usage_snapshot()
    started = time.perf_counter()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(args.cmd, stdout=stdout, stderr=stderr, text=True)
    elapsed = time.perf_counter() - started
    after = usage_snapshot()
    stop_process(gpu_proc)

    metrics = {
        "name": args.name,
        "command": args.cmd,
        "returncode": proc.returncode,
        "started_at": started_iso,
        "wall_seconds": elapsed,
        "resource": diff_usage(before, after),
        "gpu_samples": str(gpu_path) if gpu_path.exists() else None,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

