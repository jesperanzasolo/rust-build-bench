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

    def test_hermetic_that_skips_targets_is_ineligible(self):
        rs = self.records(hermetic_fresh=50, native_fresh=100)
        for r in rs:
            if r["scenario"] == "cold" and r["tool"] == "bazel":
                r["coverage"] = {"test_targets": 57}
                r["counts"] = {"executed": 43, "total": 43, "unit": "test_target"}
        d = report.decide(report.summarize(rs))
        self.assertEqual(d["per_corpus"]["c"]["verdict"], "use")
        self.assertIn("43 of the 57", d["per_corpus"]["c"]["ineligible"]["bazel"])

    def test_native_with_different_test_count_is_ineligible(self):
        rs = self.records(hermetic_fresh=90, native_fresh=100)
        for r in rs:
            if r["scenario"] == "cold":
                n = 8409 if r["tool"] == "cargo-rail" else 8227
                r["counts"] = {"executed": n, "unit": "test"}
        d = report.decide(report.summarize(rs))
        self.assertIn("8409", d["per_corpus"]["c"]["ineligible"]["cargo-rail"])


class MeasureTest(unittest.TestCase):
    def test_run_measures_and_logs(self):
        from rbb.measure import run
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "x.log"
            r = run(["sh", "-c", "echo hello; exit 3"], cwd=td, log_path=log)
            self.assertEqual(r.exit_code, 3)
            self.assertIn("hello", log.read_text())
            self.assertIsNotNone(r.wall_s)


class CheckoutTest(unittest.TestCase):
    def test_stale_generated_config_removed(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
            (ws / "crates/a").mkdir(parents=True)
            (ws / "crates/a/lib.rs").write_text("")
            git(ws, "add", "-A"); git(ws, "commit", "-q", "-m", "a")
            c1 = git(ws, "rev-parse", "HEAD")
            (ws / "crates/b").mkdir()
            (ws / "crates/b/lib.rs").write_text("")
            git(ws, "add", "-A"); git(ws, "commit", "-q", "-m", "b")
            (ws / ".git/info/exclude").write_text("BUILD.bazel\n")
            (ws / "crates/a/BUILD.bazel").write_text("x")
            (ws / "crates/b/BUILD.bazel").write_text("x")
            from rbb.corpus import checkout
            checkout(ws, c1)
            self.assertFalse((ws / "crates/b").exists())
            self.assertTrue((ws / "crates/a/BUILD.bazel").exists())


if __name__ == "__main__":
    unittest.main()


class SkipBinariesTest(unittest.TestCase):
    def _adapter(self, specs):
        import types
        from rbb.adapters.cargo import CargoAdapter
        from rbb.config import Canary, Corpus
        c = Corpus(name="t", kind="git", repo=None, commit=None, replay_commits=1, exclude_packages=[],
                   skip_tests=[], env={}, canary=Canary(), synthetic={}, extra_data={},
                   cargo_args=[], metadata_args=[], skip_binaries=specs)
        a = CargoAdapter.__new__(CargoAdapter)
        a.ctx = types.SimpleNamespace(corpus=c)
        return a, c

    def test_filterset(self):
        a, c = self._adapter(["xtask", "smol_str/tidy", "ruff/lib"])
        self.assertEqual(a.filter_args("package(=hir)"),
                         ["-E", "package(=hir) & not (package(=xtask) | (package(=smol_str) & binary(=tidy))"
                                " | (package(=ruff) & kind(lib)))"])
        self.assertTrue(c.binary_skipped("xtask", "bin", "xtask"))
        self.assertTrue(c.binary_skipped("smol_str", "test", "tidy"))
        self.assertFalse(c.binary_skipped("smol_str", "lib", "smol_str"))
        self.assertTrue(c.binary_skipped("ruff", "lib", "ruff"))
        self.assertFalse(c.binary_skipped("ruff", "test", "lib"))

    def test_no_specs_no_filter(self):
        a, _ = self._adapter([])
        self.assertEqual(a.filter_args(), [])
        self.assertEqual(a.filter_args("package(=x)"), ["-E", "package(=x)"])


class HardwareLinesTest(unittest.TestCase):
    def test_scaled_gap_reported_when_cpus_differ(self):
        summary = {"c": {"moon": {"family": "cargo-native", "replay_fresh": {"total_s": 1948}},
                         "bazel": {"family": "hermetic", "replay_fresh": {"total_s": 1327}}}}
        decision = {"per_corpus": {"c": {"best_cargo_native": "moon", "best_hermetic": "bazel", "gap_fresh": 0.319}}}
        mach = {"c": {"moon": {"cpu": "Xeon", "single": 0.529, "parallel": 0.428},
                      "bazel": {"cpu": "EPYC 9V45", "single": 0.491, "parallel": 0.351}}}
        text = "\n".join(report._hardware_lines(summary, decision, mach))
        self.assertIn("2 different CPU models", text)
        self.assertIn("+17%", text)
        self.assertIn("+32%", text)
