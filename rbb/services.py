"""Shared-cache services started by the harness.

`bazel-remote` is a REAPI (gRPC) + HTTP cache server. Bazel, Buck2 and moon all
speak REAPI, so one local server gives each of them an identical shared cache with
negligible network latency. Each (corpus, tool) gets its own server and data dir so
tools never see each other's entries.
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

from .adapters.base import Services, rm


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"service did not open port {port}")


class LocalServices(Services):
    def __init__(self, data_root: Path, log_dir: Path, tools_bin: Path):
        super().__init__()
        self._ports: dict[str, tuple[int, int]] = {}
        self.data_root = data_root
        self.log_dir = log_dir
        self.tools_bin = tools_bin

    def start(self, name: str) -> None:
        if name != "bazel-remote":
            raise ValueError(f"unknown service {name}")
        if name in self.procs:
            return
        grpc, http = self._ports.get(name) or (_free_port(), _free_port())
        self._ports[name] = (grpc, http)
        data = self.data_root / "bazel-remote"
        data.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log = open(self.log_dir / "bazel-remote.log", "ab")
        argv = [str(self.tools_bin / "bazel-remote"), "--dir", str(data), "--max_size", "100",
                "--grpc_address", f"127.0.0.1:{grpc}", "--http_address", f"127.0.0.1:{http}"]
        self.procs[name] = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
        _wait_port(grpc)
        self.endpoints["bazel-remote-grpc"] = f"grpc://127.0.0.1:{grpc}"
        self.endpoints["bazel-remote-http"] = f"http://127.0.0.1:{http}"

    def reset(self, name: str) -> None:
        """Empty a service's data (used by cold runs). The endpoint is unchanged."""
        p = self.procs.pop(name, None)
        if p is not None:
            p.terminate()
            p.wait(timeout=30)
        rm(self.data_root / name)
        self.start(name)

    def size_bytes(self, name: str) -> int:
        from .measure import dir_size_bytes
        return dir_size_bytes(self.data_root / name)
