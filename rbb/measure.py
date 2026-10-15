"""Process execution and resource measurement.

Wall time is measured around the child process. CPU time and memory are measured
*machine-wide* from /proc, not from the child's rusage, because Bazel and Buck2 do
most of their work in long-lived daemons that are not children of the command we
spawn. Machine-wide accounting is only meaningful on a dedicated machine, which is
a hard requirement of the methodology (see METHODOLOGY.md).
"""

from __future__ import annotations

import dataclasses
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def _read_proc_stat() -> tuple[int, int] | None:
    """Return (busy_jiffies, total_jiffies) for all CPUs, or None off Linux."""
    try:
        with open("/proc/stat", encoding="ascii") as f:
            fields = f.readline().split()[1:]
    except OSError:
        return None
    vals = [int(x) for x in fields]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
    total = sum(vals[:8])  # exclude guest columns, already counted in user
    return total - idle, total


def _mem_used_bytes() -> int | None:
    try:
        info = {}
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                key, val = line.split(":", 1)
                info[key] = int(val.split()[0]) * 1024
        return info["MemTotal"] - info["MemAvailable"]
    except (OSError, KeyError, ValueError):
        return None


class _MemSampler(threading.Thread):
    def __init__(self, interval: float = 0.25):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak = 0
        self.baseline = _mem_used_bytes() or 0
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            used = _mem_used_bytes()
            if used is not None and used > self.peak:
                self.peak = used
            self._halt.wait(self.interval)

    def stop(self) -> int:
        self._halt.set()
        self.join(timeout=2)
        return max(0, self.peak - self.baseline)


@dataclasses.dataclass
class CmdResult:
    argv: list[str]
    exit_code: int
    wall_s: float
    cpu_s: float | None
    peak_mem_bytes: int | None
    log_path: str | None
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def run(
    argv: list[str] | str,
    *,
    cwd: str | Path,
    env: dict[str, str] | None = None,
    log_path: str | Path | None = None,
    timeout_s: float | None = None,
    check: bool = False,
    shell: bool = False,
) -> CmdResult:
    """Run a command, stream its output to a log file, and measure it."""
    if isinstance(argv, str) and not shell:
        argv = shlex.split(argv)
    display = argv if isinstance(argv, list) else [argv]
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    log_f = None
    if log_path is not None:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        log_f = open(log_path, "ab")
        log_f.write(f"\n$ (cd {cwd} && {' '.join(map(str, display))})\n".encode())
        log_f.flush()

    sampler = _MemSampler()
    cpu0 = _read_proc_stat()
    sampler.start()
    t0 = time.perf_counter()
    timed_out = False
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=full_env,
            stdout=log_f if log_f else subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            shell=shell,
            start_new_session=True,
        )
        try:
            code = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, 9)
            code = proc.wait()
    finally:
        wall = time.perf_counter() - t0
        peak = sampler.stop()
        cpu1 = _read_proc_stat()
        if log_f:
            log_f.write(f"\n[rbb] exit={locals().get('code')} wall={wall:.2f}s\n".encode())
            log_f.close()
    cpu_s = None
    if cpu0 and cpu1:
        cpu_s = (cpu1[0] - cpu0[0]) / _CLK_TCK
    res = CmdResult(
        argv=[str(a) for a in display],
        exit_code=code,
        wall_s=wall,
        cpu_s=cpu_s,
        peak_mem_bytes=peak,
        log_path=str(log_path) if log_path else None,
        timed_out=timed_out,
    )
    if check and not res.ok:
        tail = tail_log(log_path) if log_path else ""
        raise RuntimeError(f"command failed ({code}): {' '.join(res.argv)}\n{tail}")
    return res


def capture(argv: list[str] | str, *, cwd: str | Path = ".", env: dict | None = None,
            check: bool = True, shell: bool = False) -> str:
    """Run a short command and return stdout (not measured)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    if isinstance(argv, str) and not shell:
        argv = shlex.split(argv)
    p = subprocess.run(argv, cwd=str(cwd), env=full_env, capture_output=True, text=True, shell=shell)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {argv}\n{p.stderr[-4000:]}")
    return p.stdout


def tail_log(path: str | Path | None, n: int = 60) -> str:
    if not path or not Path(path).exists():
        return ""
    with open(path, "rb") as f:
        data = f.read()[-20000:]
    return "\n".join(data.decode(errors="replace").splitlines()[-n:])


def dir_size_bytes(path: str | Path) -> int:
    total = 0
    p = Path(path)
    if not p.exists():
        return 0
    for root, _dirs, files in os.walk(p, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total
