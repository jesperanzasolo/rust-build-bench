"""Aggregate results/<run_id>/**/results.jsonl into REPORT.md and summary.json,
and apply the pre-registered decision rule (METHODOLOGY.md, "Decision rule")."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

CARGO_NATIVE = {"baseline", "cargo-native"}
THRESHOLD = 0.20   # pre-registered: a hermetic tool must beat the best Cargo-native tool by >20%


def load(run_dir: Path) -> list[dict]:
    recs = []
    for f in sorted(run_dir.rglob("results.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                recs.append(json.loads(line))
    return recs


def _timed(recs, scenario, *, exclude_seed=True):
    return [r for r in recs if r["scenario"] == scenario and "wall_s" in r
            and not (exclude_seed and r["step"] == "seed")]


def _median(xs):
    return statistics.median(xs) if xs else None


def _p90(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]


def summarize(recs: list[dict]) -> dict:
    out: dict = {}
    by = {}
    for r in recs:
        by.setdefault((r["corpus"], r["tool"]), []).append(r)
    for (corpus, tool), rs in sorted(by.items()):
        fam = rs[0]["family"]
        s = {"family": fam}
        cold = _timed(rs, "cold")
        s["cold_s"] = _median([r["wall_s"] for r in cold])
        s["cold_exit"] = cold[0]["exit_code"] if cold else None
        s["coverage"] = next((r.get("coverage") for r in cold if r.get("coverage")), None)
        s["cold_counts"] = cold[0].get("counts") if cold else None
        noop = _timed(rs, "noop")
        s["noop_s"] = _median([r["wall_s"] for r in noop])
        for sc in ("replay-warm", "replay-fresh"):
            st = _timed(rs, sc)
            walls = [r["wall_s"] for r in st]
            cpus = [r["cpu_s"] for r in st if r.get("cpu_s") is not None]
            key = sc.replace("-", "_")
            s[key] = {
                "n": len(st), "total_s": round(sum(walls), 1) if walls else None,
                "median_s": _median(walls), "p90_s": _p90(walls),
                "cpu_total_s": round(sum(cpus), 1) if cpus else None,
                "failures": sum(1 for r in st if r["exit_code"] != 0),
                "skipped": sum(1 for r in st if r.get("skipped")),
                "sync_total_s": round(sum(r.get("sync_s") or 0 for r in st), 1),
                "post_merge_total_s": round(sum((r.get("counts") or {}).get("post_merge_s") or 0 for r in st), 1),
            }
        verdicts = [r for r in rs if r["scenario"] == "canary" and r["step"].endswith(":verdict")]
        s["canary"] = {r["step"].split(":")[0]: r["canary"]["reason"] for r in verdicts}
        s["canary_ok"] = bool(verdicts) and all(r["canary"]["ok"] for r in verdicts)
        timed = [r for r in rs if "wall_s" in r and r["scenario"] != "canary"]
        s["all_steps_clean"] = bool(timed) and all(r["exit_code"] == 0 for r in timed)
        s["failed_steps"] = sum(1 for r in timed if r["exit_code"] != 0)
        states = [r for r in rs if r["step"] == "state"]
        s["state_bytes_max"] = max((sum(r["state_bytes"].values()) for r in states), default=None)
        out.setdefault(corpus, {})[tool] = s
    return out


def coverage_problem(s: dict, baseline: dict | None) -> str | None:
    """Did the tool run the whole test set? Checked on the cold run, where every tool
    runs everything. Hermetic tools must run every test target they define (a target
    that fails to build or load is silently not run); Cargo-native tools must execute
    exactly as many tests as the Cargo baseline."""
    counts = s.get("cold_counts") or {}
    defined = (s.get("coverage") or {}).get("test_targets")
    if s["family"] not in CARGO_NATIVE:
        ran = counts.get("executed", counts.get("total"))
        if defined and ran is not None and ran < defined:
            return f"ran {ran} of the {defined} test targets it defines (the rest did not build)"
        return None
    if baseline is None or s is baseline:
        return None
    b = (baseline.get("cold_counts") or {}).get("executed")
    ran = counts.get("executed")
    if b is not None and ran is not None and ran != b:
        return f"executed {ran} tests on the cold run, the Cargo baseline {b}"
    return None


def eligible(s: dict, baseline: dict | None) -> tuple[bool, str]:
    if not s["canary_ok"]:
        return False, "canary failed: " + ", ".join(f"{k}={v}" for k, v in s["canary"].items())
    cp = coverage_problem(s, baseline)
    if cp:
        return False, "different test set: " + cp
    # Only meaningful when the baseline is deterministic: if the corpus has flaky
    # tests, a single failing cold run says nothing about the tool.
    if s["cold_exit"] not in (0, None) and baseline and baseline.get("all_steps_clean"):
        return False, "cold run failed where the Cargo baseline passed every step"
    if not s["replay_fresh"]["n"]:
        return False, "no replay-fresh data"
    return True, ""


def load_exclusions(run_dir: Path) -> dict:
    """results/<run>/exclusions.toml: {corpus: {tool: reason}}. For coverage problems
    the automatic rules cannot see (a tool that ran different tests). Every entry is
    printed in the report; the decision is also shown without them."""
    f = run_dir / "exclusions.toml"
    if not f.exists():
        return {}
    import tomllib
    return tomllib.loads(f.read_text())


def decide(summary: dict, exclusions: dict | None = None) -> dict:
    exclusions = exclusions or {}
    decisions = {}
    for corpus, tools in summary.items():
        base = tools.get("cargo")
        excl = exclusions.get(corpus, {})
        elig = {t: s for t, s in tools.items() if eligible(s, base)[0] and t not in excl}
        ineligible = {t: (f"excluded: {excl[t]}" if t in excl else eligible(s, base)[1])
                      for t, s in tools.items() if t not in elig}
        native = {t: s for t, s in elig.items() if s["family"] in CARGO_NATIVE}
        hermetic = {t: s for t, s in elig.items() if s["family"] not in CARGO_NATIVE}
        if not native:
            decisions[corpus] = {"verdict": "inconclusive", "reason": "no eligible Cargo-native tool",
                                 "ineligible": ineligible}
            continue
        key = lambda kv: kv[1]["replay_fresh"]["total_s"]
        b_name, b = min(native.items(), key=key)
        d = {"best_cargo_native": b_name, "best_cargo_native_fresh_total_s": b["replay_fresh"]["total_s"],
             "ineligible": ineligible}
        if hermetic:
            h_name, h = min(hermetic.items(), key=key)
            gap_fresh = 1 - h["replay_fresh"]["total_s"] / b["replay_fresh"]["total_s"]
            bw, hw = b["replay_warm"]["total_s"], h["replay_warm"]["total_s"]
            gap_warm = (1 - hw / bw) if bw and hw else None
            d.update({"best_hermetic": h_name, "best_hermetic_fresh_total_s": h["replay_fresh"]["total_s"],
                      "gap_fresh": round(gap_fresh, 3),
                      "gap_warm": None if gap_warm is None else round(gap_warm, 3)})
            if gap_fresh > THRESHOLD:
                d["verdict"] = "build"
                d["reason"] = (f"{h_name} is {gap_fresh:.0%} faster than {b_name} on replay-fresh PR CI. "
                               "A Cargo-native tool that captures that gap without a build-system "
                               "migration has room to exist.")
            else:
                d["verdict"] = "use"
                d["reason"] = (f"No hermetic tool beats {b_name} by more than {THRESHOLD:.0%} on "
                               f"replay-fresh PR CI (best: {h_name}, {gap_fresh:+.0%}).")
        else:
            d["verdict"] = "use"
            d["reason"] = "No eligible hermetic tool to compare against."
        decisions[corpus] = d
    verdicts = {d["verdict"] for d in decisions.values()}
    overall = verdicts.pop() if len(verdicts) == 1 else "mixed"
    return {"per_corpus": decisions, "overall": overall}


def _fmt(x, unit="s"):
    if x is None:
        return "n/a"
    if unit == "s":
        return f"{x:,.1f}"
    if unit == "b":
        return f"{x / 2**30:,.1f} GiB"
    return str(x)


def machines(run_dir: Path) -> dict:
    """{corpus: {tool: {"cpu": model, "single": s, "parallel": s}}} from provenance."""
    out: dict = {}
    for f in sorted(run_dir.glob("*/*/provenance.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        cal = d.get("calibration") or {}
        out.setdefault(f.parent.parent.name, {})[f.parent.name] = {
            "cpu": (d.get("machine") or {}).get("cpu_model"),
            "single": cal.get("sha256_1GiB_single_s"),
            "parallel": cal.get("sha256_512MiB_x4_parallel_s"),
        }
    return out


def scaled_gap(summary: dict, decision: dict, mach: dict, corpus: str) -> float | None:
    """Decision gap with fresh totals scaled to the slowest machine by 4-core
    calibration, when the corpus ran on more than one CPU model; else None."""
    m = mach.get(corpus, {})
    d = decision["per_corpus"].get(corpus, {})
    b, h = d.get("best_cargo_native"), d.get("best_hermetic")
    if len({x.get("cpu") for x in m.values() if x.get("cpu")}) < 2 or not (b and h):
        return None
    if not all(m.get(t, {}).get("parallel") for t in (b, h)):
        return None
    ref = max(x["parallel"] for x in m.values() if x.get("parallel"))
    adj = {t: summary[corpus][t]["replay_fresh"]["total_s"] * ref / m[t]["parallel"] for t in (b, h)}
    return 1 - adj[h] / adj[b]


def _hardware_lines(summary: dict, decision: dict, mach: dict) -> list[str]:
    """Machine table per corpus and, when CPU models differ, the decision gap with
    times scaled by each machine's parallel calibration (a sensitivity check only;
    the pre-registered rule uses raw times)."""
    L: list[str] = []
    for corpus, tools in summary.items():
        m = mach.get(corpus, {})
        if not m:
            continue
        L += [f"### Machines, {corpus}", "",
              "| Tool | CPU | Calibration, 1 core (s) | Calibration, 4 cores (s) |", "|---|---|---|---|"]
        for t in sorted(tools):
            x = m.get(t, {})
            L.append(f"| `{t}` | {x.get('cpu') or 'n/a'} | {_fmt(x.get('single'), '')} | {_fmt(x.get('parallel'), '')} |")
        L.append("")
        cpus = {x.get("cpu") for x in m.values() if x.get("cpu")}
        d = decision["per_corpus"].get(corpus, {})
        b, h = d.get("best_cargo_native"), d.get("best_hermetic")
        gap = scaled_gap(summary, decision, mach, corpus)
        if gap is not None:
            L += [f"> {corpus}: tools ran on {len(cpus)} different CPU models. Scaled to the slowest "
                  f"machine by 4-core calibration, `{h}` vs `{b}` is {gap:+.0%} (raw: {d.get('gap_fresh', 0):+.0%}). "
                  "Treat a verdict whose gap changes side of the threshold under this scaling as inconclusive.", ""]
    return L


def render(summary: dict, decision: dict, run_dir: Path) -> str:
    L = [f"# Results: {run_dir.name}", ""]
    ov = decision["overall"]
    L += ["## Decision", ""]
    for corpus, d in decision["per_corpus"].items():
        if d["verdict"] == "use":
            head = f"**Use {d.get('best_cargo_native')}**"
        elif d["verdict"] == "build":
            head = "**Build yourself**"
        else:
            head = f"**{d['verdict'].title()}**"
        L.append(f"- **{corpus}:** {head}. {d.get('reason', '')}")
        for t, why in d.get("ineligible", {}).items():
            L.append(f"  - Not eligible: `{t}`: {why}")
    L += ["", f"Overall: **{ov}** (rule in METHODOLOGY.md, pre-registered threshold {THRESHOLD:.0%}).", ""]
    mach = machines(run_dir)
    for corpus, d in decision["per_corpus"].items():
        g = scaled_gap(summary, decision, mach, corpus)
        raw = d.get("gap_fresh")
        if g is not None and raw is not None and (raw > THRESHOLD) != (g > THRESHOLD):
            L += [f"> **{corpus}: inconclusive.** The tools ran on different CPU models; scaled by CPU "
                  f"calibration the gap is {g:+.0%} instead of {raw:+.0%}, the other side of the "
                  f"{THRESHOLD:.0%} threshold. Rerun on one CPU model before acting on it (see Machines).", ""]
    wo = decision.get("without_exclusions")
    if wo:
        L += ["Without the documented exclusions (`exclusions.toml`): " + "; ".join(
            f"{c}: {d['verdict']}" + (f" ({d.get('best_hermetic')} vs {d.get('best_cargo_native')}, "
                                      f"{d['gap_fresh']:+.0%})" if d.get("gap_fresh") is not None else "")
            for c, d in wo["per_corpus"].items()) + ".", ""]
    # Sensitivity: every hermetic tool's fresh-runner gap to the best eligible
    # Cargo-native tool, whether or not the hermetic tool was eligible.
    for corpus, d in decision["per_corpus"].items():
        bn = d.get("best_cargo_native")
        if not bn:
            continue
        bt = summary[corpus][bn]["replay_fresh"]["total_s"]
        rows = []
        for t, s_ in sorted(summary[corpus].items()):
            if s_["family"] in CARGO_NATIVE or not s_["replay_fresh"]["total_s"]:
                continue
            gap = 1 - s_["replay_fresh"]["total_s"] / bt
            why = d.get("ineligible", {}).get(t)
            rows.append(f"`{t}` {gap:+.0%}" + (f" (not eligible: {why})" if why else ""))
        if rows:
            L += [f"Sensitivity, {corpus}: fresh-runner gap to `{bn}` if counted: " + "; ".join(rows) + ".", ""]
    for corpus, tools in summary.items():
        b = tools.get("cargo")
        if b and not b["all_steps_clean"]:
            L += [f"> {corpus}: the Cargo baseline failed {b['failed_steps']} non-canary step(s), so the corpus "
                  "has failing or flaky tests. Failures are reported per tool but do not affect eligibility.", ""]
    for corpus, tools in summary.items():
        L += [f"## {corpus}", "",
              "| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |",
              "|---|---|---|---|---|---|---|"]
        for t, s in sorted(tools.items(), key=lambda kv: (kv[1]["replay_fresh"]["total_s"] or 1e18)):
            f, w = s["replay_fresh"], s["replay_warm"]
            canary = "pass" if s["canary_ok"] else ("FAIL" if s["canary"] else "n/a")
            L.append(f"| `{t}` | {_fmt(s['cold_s'])} | {_fmt(s['noop_s'])} | "
                     f"{_fmt(f['median_s'])} / {_fmt(f['p90_s'])} / {_fmt(f['total_s'])} | "
                     f"{_fmt(w['median_s'])} / {_fmt(w['total_s'])} | {canary} | {_fmt(s['state_bytes_max'], 'b')} |")
        L += ["", "| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |",
              "|---|---|---|---|---|---|"]
        for t, s in sorted(tools.items()):
            f, w = s["replay_fresh"], s["replay_warm"]
            L.append(f"| `{t}` | {_fmt(f['cpu_total_s'])} | {_fmt(w['cpu_total_s'])} | "
                     f"{f['failures']}/{w['failures']} | {_fmt(f['sync_total_s'] + w['sync_total_s'])} | "
                     f"{_fmt(f['post_merge_total_s']) if f['post_merge_total_s'] else '-'} |")
        L.append("")
    hw = _hardware_lines(summary, decision, machines(run_dir))
    if hw:
        L += ["## Machines", ""] + hw
    L += ["Raw per-step records: `**/results.jsonl`. Provenance: `**/provenance.json`.", ""]
    return "\n".join(L)


def main(run_dir: str) -> None:
    rd = Path(run_dir)
    recs = load(rd)
    if not recs:
        raise SystemExit(f"no results under {rd}")
    summary = summarize(recs)
    exclusions = load_exclusions(rd)
    decision = decide(summary, exclusions)
    decision["without_exclusions"] = decide(summary) if exclusions else None
    (rd / "summary.json").write_text(json.dumps({"summary": summary, "decision": decision,
                                                 "exclusions": exclusions}, indent=1, sort_keys=True))
    (rd / "REPORT.md").write_text(render(summary, decision, rd))
    print((rd / "REPORT.md").read_text())
