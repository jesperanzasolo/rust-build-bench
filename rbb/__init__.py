"""rust-build-bench: a tool-agnostic benchmark for Rust monorepo build/test tooling.

Only the Python standard library is used so the harness runs anywhere Python 3.11+
is available, without a package install step that could perturb measurements.
"""

__version__ = "0.1.0"
RESULT_SCHEMA = "rbb.result/v1"
