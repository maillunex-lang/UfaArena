"""Host load guard (spec §8 "не перегружать существующий VPS"). The production VPS is shared with other projects
(1 vCPU, 2 GB RAM, swap in use), so the Director reads the host's load average and available memory and scales the
AI activity down before the server feels it. Containers see the host's /proc/loadavg and /proc/meminfo; when they
are unreadable (Windows, tests) the guard is neutral."""
from __future__ import annotations

import os


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="ascii") as f:
            return f.read()
    except OSError:
        return None


def snapshot() -> dict:
    cpus = os.cpu_count() or 1
    load1 = None
    la = _read("/proc/loadavg")
    if la:
        try:
            load1 = float(la.split()[0])
        except (ValueError, IndexError):
            load1 = None
    mem_avail_mb = None
    mi = _read("/proc/meminfo")
    if mi:
        for line in mi.splitlines():
            if line.startswith("MemAvailable:"):
                try:
                    mem_avail_mb = int(line.split()[1]) // 1024
                except (ValueError, IndexError):
                    pass
                break
    return {"cpus": cpus, "load1": load1, "mem_avail_mb": mem_avail_mb}


def factor(snap: dict, s: dict) -> float:
    """1.0 = free to act; lower = the host is busy. Thresholds come from the Director settings."""
    f = 1.0
    load1, cpus, mem = snap.get("load1"), snap.get("cpus") or 1, snap.get("mem_avail_mb")
    if load1 is not None:
        per_cpu = load1 / cpus
        if per_cpu >= s["host_load_hard"] / 100:
            f *= 0.2
        elif per_cpu >= s["host_load_soft"] / 100:
            f *= 0.5
    if mem is not None:
        if mem < s["host_mem_hard_mb"]:
            f *= 0.2
        elif mem < s["host_mem_soft_mb"]:
            f *= 0.5
    return f
