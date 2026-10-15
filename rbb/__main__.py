"""Command line: python3 -m rbb {install,run,report,list}"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

from .config import REPO_ROOT, load_bench, load_corpus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rbb", description="rust-build-bench")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("install", help="install pinned tools")
    p.add_argument("--prefix", default=os.environ.get("RBB_TOOLS", str(Path.home() / ".rbb-tools")))
    p.add_argument("tools", nargs="*")

    p = sub.add_parser("run", help="run the protocol for one corpus and tool")
    p.add_argument("--corpus", required=True)
    p.add_argument("--tool", required=True)
    p.add_argument("--run-id", default=os.environ.get("RBB_RUN_ID") or dt.date.today().isoformat())
    p.add_argument("--scenarios", nargs="*", help="subset of scenarios (default: bench.toml)")
    p.add_argument("--work", default=os.environ.get("RBB_WORK", str(Path.home() / "rbb-work")))
    p.add_argument("--results", default=str(REPO_ROOT / "results"))
    p.add_argument("--tools-prefix", default=os.environ.get("RBB_TOOLS", str(Path.home() / ".rbb-tools")))
    p.add_argument("--bench", default=str(REPO_ROOT / "bench.toml"))

    p = sub.add_parser("report", help="aggregate a results directory")
    p.add_argument("run_dir")

    sub.add_parser("list", help="list corpora and tools")

    a = ap.parse_args(argv)
    if a.cmd == "install":
        from .install import install
        install(a.tools or [], Path(a.prefix))
    elif a.cmd == "run":
        from .runner import Runner
        corpus = load_corpus(a.corpus)
        bench = load_bench(Path(a.bench))
        out = Path(a.results) / a.run_id / corpus.name / a.tool
        Runner(corpus=corpus, tool=a.tool, bench=bench, run_id=a.run_id, work_root=Path(a.work),
               out_dir=out, tools_prefix=Path(a.tools_prefix), only=a.scenarios).run()
    elif a.cmd == "report":
        from .report import main as report
        report(a.run_dir)
    elif a.cmd == "list":
        from .adapters import ADAPTERS
        print("tools:   " + " ".join(ADAPTERS))
        print("corpora: " + " ".join(sorted(p.stem for p in (REPO_ROOT / "corpora").glob("*.toml"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
