import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from rbb import report
from rbb.config import Canary, Corpus, load_bench, load_corpus
from rbb.corpus import CANARY_MARK, canary_verdict, git, make_canary_commits


def corpus(**kw):
    base = dict(name="t", kind="git", repo=None, commit=None, replay_commits=1, exclude_packages=[],
                skip_tests=[], env={}, canary=Canary("up", "down"), synthetic={}, extra_data={},
                cargo_args=[], metadata_args=[], toolchain_components=[])
    base.update(kw)
    return Corpus(**base)


class CanaryTest(unittest.TestCase):
    def test_commits_and_verdicts(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
            (ws / "up/src").mkdir(parents=True)
            (ws / "up/src/lib.rs").write_text("pub fn f() {}\n")
            (ws / "down/src").mkdir(parents=True)
            (ws / "down/src/lib.rs").write_text("")
            git(ws, "add", "-A")
            git(ws, "commit", "-q", "-m", "init")
            steps = make_canary_commits(ws, corpus(), {"up": "up", "down": "down"}, {"up": "up"})
            self.assertEqual([s.label for s in steps], ["K1", "K2", "K3"])
            self.assertEqual([s.expect_failure for s in steps], [False, True, False])
            self.assertIn("RBB_CANARY: u32 = 1", (ws / "up/src/lib.rs").read_text())
            self.assertIn("up::RBB_CANARY", (ws / "down/tests/rbb_canary.rs").read_text())
            diff = git(ws, "diff", "--name-only", f"{steps[0].commit}..{steps[1].commit}")
            self.assertEqual(diff, "up/src/lib.rs")

    def test_verdicts(self):
        self.assertTrue(canary_verdict(f"x {CANARY_MARK}: expected", 101, True)["ok"])
        self.assertEqual(canary_verdict("all ok", 0, True)["reason"], "stale-pass")
        self.assertEqual(canary_verdict("other failure", 1, True)["reason"], "failed-without-canary-output")
        self.assertTrue(canary_verdict("all ok", 0, False)["ok"])
        self.assertFalse(canary_verdict(f"\x1b[31m{CANARY_MARK}\x1b[0m", 1, False)["ok"])


class ConfigTest(unittest.TestCase):
    def test_corpora_load(self):
        for name in ("ruff", "rust-analyzer", "ripgrep"):
            c = load_corpus(name)
            self.assertEqual(len(c.commit), 40)
            self.assertTrue(c.canary.upstream and c.canary.downstream)
        self.assertEqual(load_corpus("rust-analyzer").toolchain_components, ["rust-src"])

    def test_bench_loads(self):
        b = load_bench()
        self.assertEqual(b.scenarios[0], "cold")


def rec(tool, family, scenario, step, wall, exit_code=0, **kw):
    r = dict(corpus="c", tool=tool, family=family, scenario=scenario, step=step, wall_s=wall,
             exit_code=exit_code, cpu_s=wall, sync_s=0.0)
    r.update(kw)
    return r


def verdicts(tool, family, ok=True):
    return [dict(corpus="c", tool=tool, family=family, scenario="canary", step=f"warm-K{i}:verdict",
                 canary={"ok": ok, "reason": "x"}) for i in (1, 2)]


class DecisionTest(unittest.TestCase):
    def records(self, hermetic_fresh, native_fresh, hermetic_canary=True):
        rs = []
        for tool, fam, fresh in (("cargo", "baseline", 300), ("cargo-rail", "cargo-native", native_fresh),
                                 ("bazel", "hermetic", hermetic_fresh)):
            rs.append(rec(tool, fam, "cold", "s0", 100))
            rs += [rec(tool, fam, "replay-fresh", f"c{i}", fresh / 2) for i in (1, 2)]
            rs += [rec(tool, fam, "replay-warm", f"c{i}", fresh / 4) for i in (1, 2)]
            rs += verdicts(tool, fam, ok=hermetic_canary or fam != "hermetic")
        return rs

    def test_use_when_gap_small(self):
        d = report.decide(report.summarize(self.records(hermetic_fresh=90, native_fresh=100)))
        self.assertEqual(d["per_corpus"]["c"]["verdict"], "use")
        self.assertEqual(d["per_corpus"]["c"]["best_cargo_native"], "cargo-rail")

    def test_build_when_gap_large(self):
        d = report.decide(report.summarize(self.records(hermetic_fresh=50, native_fresh=100)))
        self.assertEqual(d["per_corpus"]["c"]["verdict"], "build")

    def test_ineligible_hermetic_ignored(self):
        d = report.decide(report.summarize(self.records(hermetic_fresh=10, native_fresh=100,
                                                        hermetic_canary=False)))
        self.assertEqual(d["per_corpus"]["c"]["verdict"], "use")
        self.assertIn("bazel", d["per_corpus"]["c"]["ineligible"])


class MeasureTest(unittest.TestCase):
    def test_run_measures_and_logs(self):
        from rbb.measure import run
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "x.log"
            r = run(["sh", "-c", "echo hello; exit 3"], cwd=td, log_path=log)
            self.assertEqual(r.exit_code, 3)
            self.assertIn("hello", log.read_text())
            self.assertIsNotNone(r.wall_s)


if __name__ == "__main__":
    unittest.main()
