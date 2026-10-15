"""Unit tests for rbb/gen/buck2.py, driven by a hand-written `cargo metadata` document."""

from __future__ import annotations

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rbb.adapters.buck2 import parse_action_stats, parse_test_summary  # noqa: E402
from rbb.cargo_meta import from_metadata  # noqa: E402
from rbb.config import Canary, Corpus  # noqa: E402
from rbb.gen import buck2 as gen  # noqa: E402

REG = "registry+https://github.com/rust-lang/crates.io-index"


def _t(name, kind, src, *, edition="2021", test=True, req=None):
    return {"name": name, "kind": kind, "crate_types": kind, "src_path": src,
            "edition": edition, "test": test, "required-features": req or []}


def make_workspace(root: Path) -> dict:
    """Workspace:
      crates/app   lib + bin `app` + bin `extra` (required-features) + tests/cli.rs
                   + tests/suite/main.rs, build.rs, renamed dep, dev-dep, proc-macro dep
      crates/mac   proc-macro
      crates/skip  excluded package (lib still built)
    third-party: serde 1.0.200 (features derive, std), anyhow 1.0.80 (renamed `ah`),
                 cc 1.0.0 (build-dep), tempfile (dev-dep), libz-sys (build script + links)
    """
    files = {
        "Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n\n[profile.dev]\nopt-level = 1\n\n'
                      '[profile.dev.package.insta]\nopt-level = 3\n',
        "Cargo.lock": "version = 4\n",
        "crates/app/Cargo.toml": '[package]\nname = "app"\n\n[[test]]\nname = "suite"\nharness = true\n',
        "crates/app/build.rs": "fn main() {}\n",
        "crates/app/src/lib.rs": 'pub mod util;\npub const S: &str = include_str!("../data/s.txt");\n',
        "crates/app/src/util.rs": "pub fn f() {}\n",
        "crates/app/src/main.rs": "fn main() {}\n",
        "crates/app/src/bin/extra.rs": "fn main() {}\n",
        "crates/app/data/s.txt": "hello\n",
        "crates/app/tests/cli.rs": 'const P: &str = env!("CARGO_MANIFEST_DIR");\n#[test] fn t() {}\n',
        "crates/app/tests/suite/main.rs": "mod helper;\n#[test] fn t() {}\n",
        "crates/app/tests/suite/helper.rs": "\n",
        "crates/app/tests/fixtures/a.py": "x = 1\n",
        "crates/mac/Cargo.toml": '[package]\nname = "mac"\n',
        "crates/mac/src/lib.rs": "\n",
        "crates/skip/Cargo.toml": '[package]\nname = "skip"\n',
        "crates/skip/src/lib.rs": 'pub const D: &str = include_str!("../../../docs/d.md");\n',
        "docs/d.md": "doc\n",
    }
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    r = str(root)
    app_id = f"path+file://{r}/crates/app#0.1.0"
    mac_id = f"path+file://{r}/crates/mac#0.1.0"
    skip_id = f"path+file://{r}/crates/skip#0.1.0"
    serde = f"{REG}#serde@1.0.200"
    anyhow = f"{REG}#anyhow@1.0.80"
    cc = f"{REG}#cc@1.0.0"
    tmp = f"{REG}#tempfile@3.10.0"
    libz = f"{REG}#libz-sys@1.1.0"
    win = f"{REG}#winapi@0.3.9"

    def ext(name, ver, pid, targets, links=None):
        return {"name": name, "version": ver, "id": pid, "source": REG,
                "manifest_path": f"/cargo/registry/src/{name}-{ver}/Cargo.toml",
                "targets": targets, "edition": "2021", "links": links, "authors": []}

    packages = [
        {"name": "app", "version": "0.1.0-beta.2", "id": app_id, "source": None, "edition": "2021",
         "manifest_path": f"{r}/crates/app/Cargo.toml", "links": None, "authors": ["A <a@x>"],
         "description": "The app", "homepage": None, "repository": None, "license": "MIT",
         "rust_version": "1.80",
         "targets": [
             _t("app", ["lib"], f"{r}/crates/app/src/lib.rs"),
             _t("app", ["bin"], f"{r}/crates/app/src/main.rs"),
             _t("extra", ["bin"], f"{r}/crates/app/src/bin/extra.rs", req=["extra"]),
             _t("cli", ["test"], f"{r}/crates/app/tests/cli.rs"),
             _t("suite", ["test"], f"{r}/crates/app/tests/suite/main.rs"),
             _t("build-script-build", ["custom-build"], f"{r}/crates/app/build.rs"),
         ]},
        {"name": "mac", "version": "0.1.0", "id": mac_id, "source": None, "edition": "2021",
         "manifest_path": f"{r}/crates/mac/Cargo.toml", "links": None, "authors": [],
         "targets": [_t("mac", ["proc-macro"], f"{r}/crates/mac/src/lib.rs")]},
        {"name": "skip", "version": "0.1.0", "id": skip_id, "source": None, "edition": "2018",
         "manifest_path": f"{r}/crates/skip/Cargo.toml", "links": None, "authors": [],
         "targets": [_t("skip", ["lib"], f"{r}/crates/skip/src/lib.rs", edition="2018")]},
        ext("serde", "1.0.200", serde, [_t("serde", ["lib"], "/x/src/lib.rs"),
                                        _t("build-script-build", ["custom-build"], "/x/build.rs")]),
        ext("anyhow", "1.0.80", anyhow, [_t("anyhow", ["lib"], "/x/src/lib.rs")]),
        ext("cc", "1.0.0", cc, [_t("cc", ["lib"], "/x/src/lib.rs")]),
        ext("tempfile", "3.10.0", tmp, [_t("tempfile", ["lib"], "/x/src/lib.rs")]),
        ext("libz-sys", "1.1.0", libz, [_t("libz_sys", ["lib"], "/x/src/lib.rs"),
                                        _t("build-script-build", ["custom-build"], "/x/build.rs")],
            links="z"),
        ext("winapi", "0.3.9", win, [_t("winapi", ["lib"], "/x/src/lib.rs")]),
    ]

    def dep(name, pkg, *kinds, target=None):
        return {"name": name, "pkg": pkg,
                "dep_kinds": [{"kind": k, "target": target} for k in kinds]}

    nodes = [
        {"id": app_id, "features": ["default", "fast"], "deps": [
            dep("ah", anyhow, None),
            dep("cc", cc, "build"),
            dep("mac", mac_id, None),
            dep("serde", serde, None),
            dep("skip", skip_id, None),
            dep("tempfile", tmp, "dev"),
            dep("winapi", win, None, target="cfg(windows)"),
            dep("libz_sys", libz, None, target='cfg(all(unix, target_arch = "x86_64"))'),
        ]},
        {"id": mac_id, "features": [], "deps": []},
        {"id": skip_id, "features": [], "deps": [dep("serde", serde, None)]},
        {"id": serde, "features": ["derive", "std"], "deps": []},
        {"id": anyhow, "features": ["std"], "deps": []},
        {"id": cc, "features": [], "deps": []},
        {"id": tmp, "features": [], "deps": []},
        {"id": libz, "features": ["libc"], "deps": []},
        {"id": win, "features": [], "deps": []},
    ]
    return {"packages": packages, "workspace_members": [app_id, mac_id, skip_id],
            "resolve": {"nodes": nodes, "root": None}, "workspace_root": r, "version": 1}


def make_corpus(**kw) -> Corpus:
    base = dict(name="t", kind="git", repo=None, commit=None, replay_commits=1,
                exclude_packages=["skip"], skip_tests=["slow::", "net"], env={},
                canary=Canary(), synthetic={}, extra_data={"app": ["crates/app/tests/fixtures/**"]},
                cargo_args=[], metadata_args=[])
    base.update(kw)
    return Corpus(**base)


class GenBuck2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        raw = make_workspace(cls.root)
        cls.ws = from_metadata(raw, cls.root)
        cls.files, cls.cov = gen.generate(cls.ws, make_corpus(), "1.99.0", "grpc://127.0.0.1:9092")
        cls.app = cls.files["crates/app/BUCK"]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_file_set(self):
        self.assertEqual(sorted(self.files), [
            ".buckconfig", ".buckroot", "BUCK", "crates/app/BUCK", "crates/mac/BUCK",
            "crates/skip/BUCK",
            "third-party/.gitignore", "third-party/Cargo.lock", "third-party/Cargo.toml",
            "third-party/fixups/libz-sys/fixups.toml",
            "third-party/fixups/serde/fixups.toml", "third-party/reindeer.toml",
            "third-party/top/main.rs", "toolchains/.buckconfig", "toolchains/BUCK",
            "toolchains/cargo_test.bzl", "toolchains/cargo_test_runner.py", "toolchains/platforms.bzl",
        ])

    def test_deterministic(self):
        again, cov = gen.generate(self.ws, make_corpus(), "1.99.0", "grpc://127.0.0.1:9092")
        self.assertEqual(again, self.files)
        self.assertEqual(cov, self.cov)

    def test_buckconfig(self):
        cfg = self.files[".buckconfig"]
        for line in ["[cells]", "  prelude = prelude", "  toolchains = toolchains",
                     "[external_cells]", "  prelude = bundled",
                     "  execution_platforms = toolchains//:execution_platforms",
                     "[buck2_re_client]", "  engine_address = grpc://127.0.0.1:9092",
                     "  action_cache_address = grpc://127.0.0.1:9092",
                     "  cas_address = grpc://127.0.0.1:9092", "  tls = false",
                     "  default_allow_cache_upload = true", "  digest_algorithms = SHA256"]:
            self.assertIn(line + "\n", cfg)

    def test_no_endpoint(self):
        files, _ = gen.generate(self.ws, make_corpus(), "1.99.0", None)
        self.assertNotIn("buck2_re_client", files[".buckconfig"])
        self.assertNotIn("remote_cache_enabled", files["toolchains/platforms.bzl"])

    def test_platform_executor(self):
        plat = self.files["toolchains/platforms.bzl"]
        self.assertIn("local_enabled = True,", plat)
        self.assertIn("remote_enabled = False,", plat)
        self.assertIn("remote_cache_enabled = True,", plat)
        self.assertIn("allow_cache_uploads = True,", plat)

    def test_toolchains(self):
        tc = self.files["toolchains/BUCK"]
        self.assertIn('load("@prelude//toolchains:rust.bzl", "system_rust_toolchain")', tc)
        self.assertIn('    rustc_flags = [\n        "-Copt-level=1",\n        "-Cdebuginfo=2",', tc)
        for name in ("rust", "cxx", "python_bootstrap", "genrule", "test",
                     "remote_test_execution", "execution_platforms", "cargo_test_runner"):
            self.assertIn(f'    name = "{name}",', tc)

    def test_third_party_manifest(self):
        text = self.files["third-party/Cargo.toml"]
        doc = tomllib.loads(text)
        deps = doc["dependencies"]
        # Keyed by package name; the rename lives in the first-party named_deps.
        self.assertEqual(sorted(deps), ["anyhow", "cc", "libz-sys", "serde", "tempfile"])
        self.assertEqual(deps["anyhow"], {"version": "=1.0.80",
                                      "default-features": False, "features": ["std"]})
        self.assertEqual(deps["serde"], {"version": "=1.0.200", "default-features": False,
                                         "features": ["derive", "std"]})
        self.assertEqual(doc["package"]["name"], "rust-third-party")
        self.assertNotIn("winapi", deps)          # cfg(windows) is filtered for the host
        self.assertEqual(self.cov["host_filtered_deps"], ["app -> winapi (cfg(windows))"])

    def test_lockfile_seed_and_mismatch(self):
        self.assertEqual(self.files["third-party/Cargo.lock"], "version = 4\n")
        lock = '[[package]]\nname = "serde"\nversion = "1.0.200"\n'
        mism = gen.lock_version_mismatches(self.ws, lock)
        self.assertIn("anyhow 1.0.80", mism)
        self.assertNotIn("serde 1.0.200", mism)

    def test_reindeer_toml(self):
        doc = tomllib.loads(self.files["third-party/reindeer.toml"])
        self.assertFalse(doc["precise_srcs"])
        self.assertEqual(doc["platform"], {"linux-x86_64": {"target": "x86_64-unknown-linux-gnu"}})
        self.assertEqual(doc["buck"]["rust_library"], "cargo.rust_library")
        self.assertEqual(doc["vendor"], {"gitignore_checksum_exclude": [".gitignore"]})

    def test_fixups(self):
        self.assertEqual(self.cov["crates_with_fixups"], ["libz-sys", "serde"])
        self.assertIn("buildscript.run = true\n", self.files["third-party/fixups/serde/fixups.toml"])
        libz = tomllib.loads(self.files["third-party/fixups/libz-sys/fixups.toml"])
        self.assertEqual(libz["buildscript"]["run"], {"rustc_link_lib": True, "rustc_link_search": True})

    def test_library(self):
        a = self.app
        self.assertIn('rust_library(\n    name = "app",', a)
        self.assertIn('    crate = "app",', a)
        self.assertIn('    crate_root = "src/lib.rs",', a)
        self.assertIn('    features = [\n        "default",\n        "fast",\n    ],', a)
        self.assertIn('    named_deps = {\n        "ah": "//third-party:anyhow",\n    },', a)
        lib = a.split('rust_library(\n    name = "app",')[1].split("\n)\n")[0]
        self.assertIn('"//crates/mac:mac"', lib)
        self.assertIn('"//crates/skip:skip"', lib)
        self.assertIn('"//third-party:serde"', lib)
        self.assertIn('"//third-party:libz-sys"', lib)
        self.assertNotIn("tempfile", lib)           # dev-dependency
        self.assertNotIn('"//third-party:cc"', lib)  # build-dependency
        self.assertIn('    srcs = glob(["src/**/*.rs"]) + ["data/s.txt"],', lib)
        self.assertIn('"@$(location :app-build-script-run[rustc_flags])"', lib)
        self.assertIn('"OUT_DIR": "$(location :app-build-script-run[out_dir])"', lib)
        self.assertIn('"CARGO_PKG_VERSION_PRE": "beta.2"', lib)
        self.assertIn('"CARGO_PKG_AUTHORS": "A <a@x>"', lib)

    def test_proc_macro(self):
        m = self.files["crates/mac/BUCK"]
        self.assertIn("    proc_macro = True,", m)
        self.assertIn('"--extern=proc_macro"', m.split("rust_test(")[1])

    def test_build_script(self):
        a = self.app
        bs = a.split('rust_binary(\n    name = "app-build-script-build",')[1].split("\n)\n")[0]
        self.assertIn('    crate = "build_script_build",', bs)
        self.assertIn('"//third-party:cc"', bs)
        self.assertNotIn("features", bs)
        self.assertIn('load("@prelude//rust:cargo_buildscript.bzl", "buildscript_run")', a)
        run = a.split('buildscript_run(\n    name = "app-build-script-run",')[1].split("\n)\n")[0]
        self.assertIn('    buildscript_rule = ":app-build-script-build",', run)
        self.assertIn('    manifest_dir = ":app-manifest-dir",', run)
        self.assertIn('    version = "0.1.0-beta.2",', run)
        self.assertEqual(self.cov["build_scripts"], ["app"])

    def test_binaries_and_required_features(self):
        a = self.app
        self.assertIn('rust_binary(\n    name = "app-bin",', a)
        self.assertNotIn('"extra-bin"', a)
        self.assertIn({"target": "//crates/app:extra-bin", "reason": "required-features not enabled"},
                      self.cov["skipped"])

    def test_integration_tests(self):
        a = self.app
        cli = a.split('rust_test(\n    name = "cli-test-inner",')[1].split("\n)\n")[0]
        self.assertIn('    crate_root = "tests/cli.rs",', cli)
        self.assertIn('"CARGO_BIN_EXE_app": "$(location :app-bin)"', cli)
        self.assertIn('"//third-party:tempfile"', cli)
        self.assertIn('"//crates/app:app"', cli)
        self.assertIn('    labels = ["rbb_inner_test"],', cli)
        # env!("CARGO_MANIFEST_DIR") in the test: point it at the package tree.
        self.assertIn('"CARGO_MANIFEST_DIR": "$(location :app-manifest-dir)"', cli)
        self.assertIn('":app-manifest-dir"', cli.split("resources = ")[1])
        self.assertIn('"//crates/app:rbb-extra-data-app-0"', cli)
        suite = a.split('rust_test(\n    name = "suite-test-inner",')[1].split("\n)\n")[0]
        self.assertIn('glob(["tests/**/*.rs"])', suite)
        self.assertIn('    crate_root = "tests/suite/main.rs",', suite)
        wrapper = a.split('cargo_test(\n    name = "cli-test",')[1].split("\n)\n")[0]
        self.assertIn('    test = ":cli-test-inner",', wrapper)
        self.assertIn('    manifest_dir = "crates/app",', wrapper)
        self.assertIn('    args = [\n        "--skip",\n        "slow::",\n        "--skip",\n        "net",\n    ],', wrapper)

    def test_unit_tests(self):
        a = self.app
        unit = a.split('rust_test(\n    name = "app-unittest-inner",')[1].split("\n)\n")[0]
        self.assertIn('    crate_root = "src/lib.rs",', unit)
        self.assertNotIn('"//crates/app:app"', unit)
        self.assertIn('"//third-party:tempfile"', unit)
        self.assertIn('rust_test(\n    name = "app-bin-unittest-inner",', a)
        self.assertEqual(self.cov["test_targets_by_kind"], {"lib": 2, "bin": 1, "test": 2})
        self.assertEqual(self.cov["test_targets"], 5)

    def test_excluded_package(self):
        s = self.files["crates/skip/BUCK"]
        self.assertIn('rust_library(\n    name = "skip",', s)
        self.assertNotIn("rust_test(", s)
        self.assertIn({"target": "//crates/skip:skip-unittest", "reason": "package excluded by corpus"},
                      self.cov["skipped"])

    def test_include_outside_package(self):
        s = self.files["crates/skip/BUCK"]
        # docs/ has no BUCK file, so the root package owns docs/d.md.
        self.assertIn('        "//:rbb-export-docs_d.md": "docs/d.md",', s)
        self.assertIn('        "src/lib.rs": "crates/skip/src/lib.rs",', s)
        self.assertIn('    crate_root = "crates/skip/src/lib.rs",', s)
        self.assertIn('    edition = "2018",', s)
        d = self.files["BUCK"]
        self.assertIn('export_file(\n    name = "rbb-export-docs_d.md",', d)
        self.assertIn('    src = "docs/d.md",', d)
        self.assertEqual(self.cov["mapped_srcs_targets"], ["//crates/skip:skip"])

    def test_include_inside_package_is_a_src(self):
        lib = self.app.split('rust_library(\n    name = "app",')[1].split("\n)\n")[0]
        self.assertIn('"data/s.txt"', lib)

    def test_vendor_include_fixups(self):
        vendor = self.root / "third-party" / "vendor" / "anyhow-1.0.80"
        (vendor / "src").mkdir(parents=True, exist_ok=True)
        (vendor / "Cargo.toml").write_text('[package]\nname = "anyhow"\nversion = "1.0.80"\n')
        (vendor / "src" / "lib.rs").write_text('const A: &str = include_str!("../README.md");\n'
                                               'include!("gen.rs");\n')
        (vendor / "README.md").write_text("x\n")
        (vendor / "src" / "gen.rs").write_text("\n")
        scanned = gen.scan_vendor_includes(self.root / "third-party" / "vendor")
        self.assertEqual(scanned, {"anyhow": ["README.md"]})
        files, cov = gen.generate(self.ws, make_corpus(), "1.99.0", None, vendor_extra_srcs=scanned)
        self.assertIn('extra_srcs = ["README.md"]\n', files["third-party/fixups/anyhow/fixups.toml"])
        self.assertIn("anyhow", cov["crates_with_fixups"])
        import shutil
        shutil.rmtree(self.root / "third-party")

    def test_cfg_eval(self):
        cfg = gen.parse_cfg(gen.DEFAULT_HOST_CFG)
        t = gen.DEFAULT_HOST_TRIPLE
        self.assertTrue(gen.cfg_matches(None, cfg, t))
        self.assertTrue(gen.cfg_matches("cfg(unix)", cfg, t))
        self.assertFalse(gen.cfg_matches("cfg(windows)", cfg, t))
        self.assertTrue(gen.cfg_matches('cfg(all(not(target_os = "windows"), any(target_arch = "x86_64", '
                                        'target_arch = "aarch64")))', cfg, t))
        self.assertFalse(gen.cfg_matches('cfg(target_vendor = "apple")', cfg, t))
        self.assertTrue(gen.cfg_matches("x86_64-unknown-linux-gnu", cfg, t))
        self.assertFalse(gen.cfg_matches("wasm32-unknown-unknown", cfg, t))

    def test_profile_flags(self):
        base, per_pkg, star = gen.profile_rustc_flags(self.ws)
        self.assertEqual(base[:2], ["-Copt-level=1", "-Cdebuginfo=2"])
        self.assertEqual(per_pkg, {"insta": ["-Copt-level=3"]})
        self.assertEqual(star, [])

    def test_runner(self):
        py = self.files["toolchains/cargo_test_runner.py"]
        self.assertIn('os.environ["CARGO_MANIFEST_DIR"] = os.path.abspath(pkg_dir)', py)
        self.assertIn('INSTA_WORKSPACE_ROOT', py)
        bzl = self.files["toolchains/cargo_test.bzl"]
        self.assertIn("ExternalRunnerTestInfo(", bzl)


class ParseTest(unittest.TestCase):
    def test_summary(self):
        log = ("Build ID: x\nCache hits: 87%\nCommands: 120 (cached: 100, remote: 0, local: 20)\n"
               "Tests finished: Pass 12. Fail 2. Timeout 0. Fatal 1. Skip 0. Omit 0. "
               "Infra Failure 0. Build failure 3\n")
        c = parse_test_summary(log)
        self.assertEqual(c["passed"], 12)
        self.assertEqual(c["failed"], 2)
        self.assertEqual(c["fatal"], 1)
        self.assertEqual(c["build_failures"], 3)
        self.assertEqual(c["executed"], 15)
        self.assertEqual(c["listing_failed"], 0)
        s = parse_action_stats(log)
        self.assertEqual(s, {"actions": 120, "hits": 100, "misses": 20, "remote": 0, "local": 20,
                             "hit_percent": 87})

    def test_summary_listing_fail(self):
        c = parse_test_summary("Tests finished: Listing Fail 1. Pass 0. Fail 0. Timeout 0. Fatal 0. "
                               "Skip 0. Omit 0. Infra Failure 0. Build failure 0")
        self.assertEqual(c["listing_failed"], 1)

    def test_no_summary(self):
        self.assertEqual(parse_test_summary("error"), {})


if __name__ == "__main__":
    unittest.main()
