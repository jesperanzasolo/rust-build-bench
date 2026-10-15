"""Tests for rbb/gen/bazel.py against a hand-written `cargo metadata` document."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rbb import cargo_meta  # noqa: E402
from rbb.config import Canary, Corpus  # noqa: E402
from rbb.gen import bazel as gen  # noqa: E402

REG = "registry+https://github.com/rust-lang/crates.io-index"


def _target(name, kind, src, *, edition="2021", test=True, req=None):
    t = {"name": name, "kind": kind, "crate_types": kind if kind != ["proc-macro"] else ["proc-macro"],
         "src_path": src, "edition": edition, "doctest": False, "test": test}
    if req:
        t["required-features"] = req
    return t


def make_metadata(root: Path) -> dict:
    r = str(root)

    def pid(name, ver="0.1.0"):
        return f"path+file://{r}/crates/{name}#{ver}"

    ext = lambda n, v: f"{REG}#{n}@{v}"  # noqa: E731
    packages = [
        {"name": "core-lib", "version": "0.1.0", "id": pid("core-lib"), "edition": "2021",
         "manifest_path": f"{r}/crates/core-lib/Cargo.toml", "links": None,
         "features": {"default": ["fast"], "fast": [], "extra": ["dep:serde"]},
         "dependencies": [
             {"name": "serde", "rename": None, "kind": None, "optional": True, "target": None},
             {"name": "rand", "rename": "rng", "kind": None, "optional": False, "target": None},
             {"name": "my-macros", "rename": None, "kind": None, "optional": False, "target": None},
             {"name": "tempfile", "rename": None, "kind": "dev", "optional": False, "target": None},
             {"name": "cc", "rename": None, "kind": "build", "optional": False, "target": None},
         ],
         "targets": [
             _target("core_lib", ["lib"], f"{r}/crates/core-lib/src/lib.rs"),
             _target("core-cli", ["bin"], f"{r}/crates/core-lib/src/main.rs"),
             _target("extra-tool", ["bin"], f"{r}/crates/core-lib/src/bin/extra.rs", req=["extra"]),
             _target("smoke", ["test"], f"{r}/crates/core-lib/tests/smoke.rs"),
             _target("suite", ["test"], f"{r}/crates/core-lib/tests/suite/main.rs"),
             _target("shared", ["test"], f"{r}/crates/core-lib/tests/shared.rs"),
             _target("build-script-build", ["custom-build"], f"{r}/crates/core-lib/build.rs"),
         ]},
        {"name": "my-macros", "version": "0.2.0", "id": pid("my-macros", "0.2.0"), "edition": "2018",
         "manifest_path": f"{r}/crates/my-macros/Cargo.toml", "links": None, "features": {},
         "dependencies": [{"name": "quote", "rename": None, "kind": None, "optional": False, "target": None}],
         "targets": [_target("my_macros", ["proc-macro"], f"{r}/crates/my-macros/src/lib.rs",
                             edition="2018")]},
        {"name": "fuzzing", "version": "0.0.0", "id": pid("fuzzing", "0.0.0"), "edition": "2021",
         "manifest_path": f"{r}/crates/fuzzing/Cargo.toml", "links": None, "features": {},
         "dependencies": [{"name": "core-lib", "rename": "core", "kind": None, "optional": False,
                           "target": None}],
         "targets": [_target("fuzzing", ["lib"], f"{r}/crates/fuzzing/src/lib.rs"),
                     _target("fz", ["test"], f"{r}/crates/fuzzing/tests/fz.rs")]},
    ]
    for n, v, kind in (("serde", "1.0.0", ["lib"]), ("rand", "0.8.5", ["lib"]),
                       ("quote", "1.0.0", ["lib"]), ("tempfile", "3.0.0", ["lib"]),
                       ("cc", "1.0.0", ["lib"])):
        packages.append({"name": n, "version": v, "id": ext(n, v), "edition": "2021",
                         "manifest_path": f"/reg/{n}/Cargo.toml", "features": {}, "dependencies": [],
                         "targets": [_target(n, kind, f"/reg/{n}/src/lib.rs")]})

    def dep(name, pkg, kinds):
        return {"name": name, "pkg": pkg, "dep_kinds": [{"kind": k, "target": None} for k in kinds]}

    nodes = [
        {"id": pid("core-lib"), "features": ["default", "fast"], "deps": [
            dep("rng", ext("rand", "0.8.5"), [None]),
            dep("my_macros", pid("my-macros", "0.2.0"), [None]),
            dep("tempfile", ext("tempfile", "3.0.0"), ["dev"]),
            # Both a build- and a dev-dependency: crate_universe drops it from the build map.
            dep("cc", ext("cc", "1.0.0"), ["build", "dev"]),
        ]},
        {"id": pid("my-macros", "0.2.0"), "features": [], "deps": [dep("quote", ext("quote", "1.0.0"), [None])]},
        {"id": pid("fuzzing", "0.0.0"), "features": [], "deps": [dep("core", pid("core-lib"), [None])]},
    ]
    return {"packages": packages, "workspace_members": [p["id"] for p in packages[:3]],
            "resolve": {"nodes": nodes, "root": None}, "workspace_root": r, "version": 1}


def write_tree(root: Path) -> None:
    files = {
        "Cargo.toml": ('[workspace]\nmembers = ["crates/*"]\n'
                       '[profile.dev]\nopt-level = 1\ndebug = "line-tables-only"\n'
                       '[profile.dev.package.rand]\nopt-level = 3\n'
                       '[profile.dev.package.my-macros]\nopt-level = 2\n'),
        "Cargo.lock": "version = 4\n",
        "shared/data.txt": "hello\n",
        "crates/core-lib/Cargo.toml": '[package]\nname = "core-lib"\nversion = "0.1.0"\n',
        "crates/core-lib/build.rs": "fn main() {}\n",
        "crates/core-lib/src/lib.rs": textwrap.dedent('''\
            pub const DATA: &str = include_str!("../../../shared/data.txt");
            pub const LOCAL: &str = include_str!("table.txt");
        '''),
        "crates/core-lib/src/table.txt": "t\n",
        "crates/core-lib/src/main.rs": "fn main() {}\n",
        "crates/core-lib/src/bin/extra.rs": "fn main() {}\n",
        "crates/core-lib/tests/smoke.rs": "mod shared;\n#[test] fn t() {}\n",
        "crates/core-lib/tests/shared.rs": "#[test] fn s() {}\n",
        "crates/core-lib/tests/suite/main.rs": "mod helper;\n",
        "crates/core-lib/tests/suite/helper.rs": "",
        "crates/my-macros/Cargo.toml": '[package]\nname = "my-macros"\nversion = "0.2.0"\n',
        "crates/my-macros/src/lib.rs": "",
        "crates/fuzzing/Cargo.toml": ('[package]\nname = "fuzzing"\nversion = "0.0.0"\n'
                                      '[[test]]\nname = "fz"\nharness = false\n'),
        "crates/fuzzing/src/lib.rs": "",
        "crates/fuzzing/tests/fz.rs": "fn main() {}\n",
    }
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def corpus(**kw) -> Corpus:
    base = dict(name="t", kind="git", repo=None, commit=None, replay_commits=1,
                exclude_packages=["fuzzing"], skip_tests=["slow_"], env={"RUST_MIN_STACK": "8388608"},
                canary=Canary(), synthetic={}, extra_data={"core-lib": ["shared/**"]},
                cargo_args=[], metadata_args=[])
    base.update(kw)
    return Corpus(**base)


class GenBazelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name).resolve()
        write_tree(root)
        cls.root = root
        cls.ws = cargo_meta.from_metadata(make_metadata(root), root)
        cls.files, cls.cov = gen.generate(
            cls.ws, corpus(), rust_version="1.99.0", rules_rust_version="0.74.0",
            remote_cache="grpc://127.0.0.1:9092", output_user_root="/w/bazel-root",
            repository_cache="/s/bazel-repo-cache", rust_sha256s={"rustc-1.99.0-x.tar.xz": "ab"})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_file_set(self):
        self.assertEqual(sorted(self.files), [
            ".bazelignore", ".bazelrc", ".bazelversion", "BUILD.bazel", "MODULE.bazel",
            "crates/core-lib/BUILD.bazel", "crates/fuzzing/BUILD.bazel", "crates/my-macros/BUILD.bazel",
            "rbb_test_launcher.sh"])
        self.assertEqual(self.files[".bazelversion"], "9.3.0\n")

    def test_deterministic(self):
        files2, cov2 = gen.generate(
            self.ws, corpus(), rust_version="1.99.0", rules_rust_version="0.74.0",
            remote_cache="grpc://127.0.0.1:9092", output_user_root="/w/bazel-root",
            repository_cache="/s/bazel-repo-cache", rust_sha256s={"rustc-1.99.0-x.tar.xz": "ab"})
        self.assertEqual(files2, self.files)
        self.assertEqual(cov2, self.cov)

    def test_module(self):
        m = self.files["MODULE.bazel"]
        self.assertIn('bazel_dep(\n    name = "rules_rust",\n    version = "0.74.0",\n)', m)
        self.assertIn('rust.toolchain(\n    edition = "2021",', m)
        self.assertIn('versions = ["1.99.0"],', m)
        self.assertIn('"rustc-1.99.0-x.tar.xz": "ab"', m)
        self.assertIn('register_toolchains("@rust_toolchains//:all")', m)
        self.assertIn('crate = use_extension("@rules_rust//crate_universe:extensions.bzl", "crate")', m)
        self.assertIn('cargo_lockfile = "//:Cargo.lock",', m)
        self.assertIn(textwrap.indent(textwrap.dedent('''\
            manifests = [
                "//:Cargo.toml",
                "//crates/core-lib:Cargo.toml",
                "//crates/fuzzing:Cargo.toml",
                "//crates/my-macros:Cargo.toml",
            ],'''), "    "), m)
        self.assertIn('use_repo(crate, "crates")', m)
        self.assertIn('lockfile = "//:cargo-bazel-lock.json",', m)

    def test_bazelrc(self):
        rc = self.files[".bazelrc"]
        for line in ("startup --output_user_root=/w/bazel-root",
                     "common --repository_cache=/s/bazel-repo-cache",
                     "build --remote_cache=grpc://127.0.0.1:9092",
                     "build --remote_upload_local_results", "build --keep_going",
                     "test --test_output=errors", "common --color=no", "common --curses=no",
                     "test --build_tests_only", "test --test_env=RUST_MIN_STACK=8388608",
                     "test --run_under=//:rbb_test_launcher"):
            self.assertIn(line + "\n", rc)
        self.assertNotIn("disk_cache", rc)
        for line in ("build --@rules_rust//rust/settings:extra_rustc_flag=-Copt-level=1",
                     "build --@rules_rust//rust/settings:extra_rustc_flag=-Cdebuginfo=line-tables-only",
                     "build --@rules_rust//rust/settings:extra_rustc_flag=-Cdebug-assertions=on",
                     "build --@rules_rust//rust/settings:extra_rustc_flag=-Coverflow-checks=on",
                     "build --@rules_rust//rust/settings:per_crate_rustc_flag="
                     "external/rules_rust++crate+crates__rand-0.8.5/@-Copt-level=3",
                     "build --@rules_rust//rust/settings:per_crate_rustc_flag=//crates/my-macros:@-Copt-level=2"):
            self.assertIn(line + "\n", rc)

    def test_library(self):
        b = self.files["crates/core-lib/BUILD.bazel"]

        self.assertIn(textwrap.dedent('''\
            rust_library(
                name = "core-lib",
                aliases = aliases(normal = True, proc_macro = True),'''), b)
        self.assertIn('crate_features = [\n        "default",\n        "fast",\n    ],', b)
        self.assertIn('crate_name = "core_lib",', b)
        self.assertIn('crate_root = "src/lib.rs",', b)
        self.assertIn('deps = all_crate_deps(normal = True) + [":core-lib_bs"],', b)
        self.assertIn('proc_macro_deps = all_crate_deps(proc_macro = True) + ["//crates/my-macros:my-macros"],', b)
        self.assertIn('"src/table.txt"', b)
        self.assertIn('"//:rbb_include_shared_data_txt"', b)
        self.assertIn('version = "0.1.0",', b)

    def test_build_script(self):
        b = self.files["crates/core-lib/BUILD.bazel"]
        self.assertIn('load("@rules_rust//cargo:defs.bzl", "cargo_build_script", "cargo_toml_env_vars")', b)
        self.assertIn('cargo_build_script(\n    name = "core-lib_bs",', b)
        self.assertIn('deps = all_crate_deps(build = True) + crate_deps(["cc"]),', b)
        self.assertIn('load("@crates//:defs.bzl", "aliases", "all_crate_deps", "crate_deps")', b)
        self.assertIn('crate_root = "build.rs",', b)
        self.assertIn('pkg_name = "core-lib",', b)

    def test_bins_and_required_features(self):
        b = self.files["crates/core-lib/BUILD.bazel"]
        self.assertIn('rust_binary(\n    name = "core-cli",', b)
        self.assertIn('deps = all_crate_deps(normal = True) + [\n        ":core-lib",\n        ":core-lib_bs",\n    ],', b)
        self.assertNotIn('"extra-tool"', b)
        self.assertIn({"package": "core-lib", "target": "extra-tool", "kind": "bin",
                       "reason": "required-features not enabled: ['extra']"}, self.cov["skipped"])
        # The bin's sources do not include other bins'.
        self.assertIn('rust_test(\n    name = "core-cli_bin_unit_test",\n', b)

    def test_tests(self):
        b = self.files["crates/core-lib/BUILD.bazel"]
        self.assertIn(textwrap.dedent('''\
            rust_test(
                name = "core-lib_unit_test",
                args = [
                    "--skip",
                    "slow_",
                ],
                crate = ":core-lib",'''), b)
        self.assertIn('deps = all_crate_deps(normal_dev = True),', b)
        self.assertIn('rust_test(\n    name = "smoke_test",', b)
        self.assertIn('crate_root = "tests/smoke.rs",', b)
        # smoke.rs declares `mod shared;`, so shared.rs (also a test root) stays in its srcs.
        self.assertIn('srcs = glob(["tests/**/*.rs"], exclude = ["tests/suite/**"], allow_empty = True),', b)
        self.assertIn('crate_root = "tests/suite/main.rs",', b)
        self.assertIn('srcs = glob(["tests/**/*.rs"], exclude = [\n        "tests/shared.rs",\n        "tests/smoke.rs",\n    ], allow_empty = True),', b)
        self.assertIn('"CARGO_BIN_EXE_core-cli": "$(rootpath :core-cli)",', b)
        self.assertIn('"CARGO_BIN_EXE_core-cli": "../../$(rootpath :core-cli)",', b)
        self.assertIn('"CARGO_MANIFEST_DIR": "%s/crates/core-lib",' % self.root.as_posix(), b)
        self.assertIn('data = [\n        "//:rbb_extra_data_core_lib",\n        ":core-cli",\n        ":rbb_all_files",\n    ],', b)
        self.assertIn('filegroup(\n    name = "rbb_extra_data_core_lib",\n    srcs = glob(["shared/**"], allow_empty = True),', self.files["BUILD.bazel"])
        self.assertEqual(self.cov["test_targets"], 6)

    def test_proc_macro(self):
        b = self.files["crates/my-macros/BUILD.bazel"]
        self.assertIn('rust_proc_macro(\n    name = "my-macros",', b)
        self.assertIn('edition = "2018",', b)
        self.assertIn('rust_test(\n    name = "my-macros_unit_test",', b)

    def test_excluded_package_and_renamed_first_party_dep(self):
        b = self.files["crates/fuzzing/BUILD.bazel"]
        self.assertIn('rust_library(\n    name = "fuzzing",\n    aliases = {\n        "//crates/core-lib:core-lib": "core",\n    },', b)
        self.assertNotIn("rust_test(", b)
        self.assertIn('filegroup(\n    name = "rbb_all_files",', b)
        self.assertTrue(self.cov["per_package"]["fuzzing"]["excluded"])

    def test_root_build(self):
        b = self.files["BUILD.bazel"]
        self.assertIn('sh_binary(\n    name = "rbb_test_launcher",', b)
        self.assertIn('filegroup(\n    name = "rbb_include_shared_data_txt",\n    srcs = glob(["shared/data.txt"], allow_empty = True),', b)
        self.assertIn('"Cargo.lock",', b)

    def test_launcher(self):
        s = self.files["rbb_test_launcher.sh"]
        self.assertTrue(s.startswith("#!/usr/bin/env bash\n"))
        self.assertIn('export INSTA_WORKSPACE_ROOT="$root"', s)
        self.assertIn('cp -RL --link -- "$runfiles/." "$root/"', s)
        self.assertIn('cd "$CARGO_MANIFEST_DIR"', s)

    def test_harness_false(self):
        ws = cargo_meta.from_metadata(make_metadata(self.root), self.root)
        files, _ = gen.generate(ws, corpus(exclude_packages=[]), rust_version="1.99.0",
                                rules_rust_version="0.74.0", remote_cache=None,
                                output_user_root="/r", repository_cache="/c")
        b = files["crates/fuzzing/BUILD.bazel"]
        self.assertIn('rust_test(\n    name = "fz_test",', b)
        self.assertIn("use_libtest_harness = False,", b)
        self.assertNotIn("remote_cache", files[".bazelrc"])

    def test_cfg_matches(self):
        t = "x86_64-unknown-linux-gnu"
        self.assertTrue(gen.cfg_matches("cfg(unix)", t))
        self.assertFalse(gen.cfg_matches("cfg(windows)", t))
        self.assertFalse(gen.cfg_matches('cfg(target_os = "macos")', t))
        self.assertTrue(gen.cfg_matches('cfg(any(target_os = "linux", target_os = "macos"))', t))
        self.assertFalse(gen.cfg_matches('cfg(all(unix, not(target_os = "linux")))', t))
        self.assertTrue(gen.cfg_matches('cfg(target_arch = "wasm32")', "wasm32-unknown-unknown"))

    def test_bazel_counts(self):
        from rbb.adapters.bazel import parse_bazel_test_counts
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("\n$ (cd /w && bazel test //...)\n"
                    "//a:x_test                                       (cached) PASSED in 0.1s\n"
                    "//a:y_test                                                PASSED in 0.2s\n"
                    "//b:z_test                                                FAILED in 0.3s\n"
                    "//b:w_test                                       FAILED TO BUILD\n"
                    "Executed 2 out of 4 tests: 2 tests pass, 1 fails locally and 1 fails to build.\n")
        c = parse_bazel_test_counts(f.name)
        Path(f.name).unlink()
        self.assertEqual(c["executed"], 2)
        self.assertEqual(c["total"], 4)
        self.assertEqual(c["failed_to_build"], 1)
        self.assertEqual(c["cached"], 1)
        self.assertEqual(c["passed"], 2)
        self.assertEqual(c["failed"], 1)
        self.assertEqual(c["unit"], "test_target")


if __name__ == "__main__":
    unittest.main()
