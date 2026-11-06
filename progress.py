"""Per-profile progress: current level vs goal + trend + what to practice next.

    python progress.py --profile levitate
    python progress.py --profile levitate --write   # also writes PROGRESS.md
    python progress.py --llm                        # per-brief LLM funnel breakdown

Reads every history source, filters it to one profile, and shows each metric's
"now" (mean of the last N rows), its goal, and whether the trend is improving /
declining / plateau. Then prints a coach that maps anything off-target to the
exact drill command to run.
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
from pathlib import Path

import profiles
import trend as _trend  # reuse trend._num / _filler_rate

ROOT = Path(__file__).resolve().parent
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))

# metric -> (goal, shrink). shrink=True means LOWER is better (latency/filler/onset).
GOALS = {
    "criteria/5": (5, False),
    "opener_latency_s": (1.5, True),
    "ack_rate_%": (100, False),
    "filler_rate_per100": (3, True),
    "reflex_%": (100, False),
    "median_onset_s": (2.0, True),
    "obj_ok_fast_%": (100, False),
    "star_solid_%": (100, False),
    "narrative_airtight_%": (100, False),
    "drill_hit_%": (100, False),
    "cost_fast_%": (100, False),
    "riq_pass_%": (100, False),
    "hook_%": (100, False),
    "challenge_%": (100, False),
    "cta_%": (100, False),
    "fallback_free_%": (100, False),
}

ORDER = ["criteria/5", "opener_latency_s", "ack_rate_%", "filler_rate_per100",
         "reflex_%", "median_onset_s", "obj_ok_fast_%",
         "star_solid_%", "narrative_airtight_%", "drill_hit_%", "cost_fast_%",
         "riq_pass_%", "hook_%", "challenge_%", "cta_%", "fallback_free_%"]


def _csv_rows(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _profile_rows(path: Path, profile: str) -> list:
    rows = _csv_rows(path)
    return [r for r in rows if (r.get("profile") or "procore") == profile]


# ---------------------------------------------------------------------------
# Per-source per-row numeric series, preserving row order.
# ---------------------------------------------------------------------------

def full_series(rows):
    return {
        "criteria/5": [_trend._num(r.get("criteria_passed")) for r in rows],
        "opener_latency_s": [_trend._num(r.get("opener_latency")) for r in rows],
        "ack_rate_%": [_trend._num(r.get("ack_rate")) for r in rows],
        "filler_rate_per100": [_trend._filler_rate(r.get("filler_rate")) for r in rows],
    }


def objection_series(rows):
    return {
        "reflex_%": [100 if r.get("reflex") == "Y" else 0 for r in rows],
        "median_onset_s": [_trend._num(r.get("onset")) for r in rows],
        "obj_ok_fast_%": [100 if (r.get("verdict") or "") in ("OK", "FAST", "CUT-IN", "HIT") else 0
                          for r in rows],
    }


def star_series(rows):
    return {"star_solid_%": [100 if r.get("ok") == "Y" else 0 for r in rows]}


def narrative_series(rows):
    return {"narrative_airtight_%": [100 if r.get("ok") == "Y" else 0 for r in rows]}


def drill_series(rows):
    onset = [_trend._num(r.get("onset")) for r in rows]
    return {
        "drill_hit_%": [100 if r.get("cost_question") == "Y" else 0 for r in rows],
        "cost_fast_%": [100 if (r.get("cost_question") == "Y" and (o or 99) <= 2.0)
                        else 0 for r, o in zip(rows, onset)],
    }


LLM_HISTORY = "llm_history.csv"
LLM_LEVEL = {"STRONG": 100.0, "PASS": 50.0, "FAIL": 0.0}
_RIQ_COLUMNS = ("riq_hook", "riq_challenge", "riq_cta")
_LLM_METRICS = frozenset(("riq_pass_%", "hook_%", "challenge_%", "cta_%",
                          "fallback_free_%"))


def _level(raw) -> float:
    """STRONG -> 100, PASS -> 50, FAIL/blank/missing -> 0."""
    return LLM_LEVEL.get((raw or "").strip(), 0.0)


def llm_series(rows) -> dict:
    """The LLM funnel (llm_history.csv) - global, the csv has no profile column.

    riq_pass_% is criteria_passed/5 as a percent; hook/challenge/cta grade the
    R+I+Q beats STRONG=100 / PASS=50 / FAIL=0 (missing/blank -> 0);
    fallback_free_% is 100 when the rep ran without a model fallback ('N')."""
    return {
        "riq_pass_%": [float(r.get("criteria_passed") or 0) / 5 * 100 for r in rows],
        "hook_%": [_level(r.get("riq_hook")) for r in rows],
        "challenge_%": [_level(r.get("riq_challenge")) for r in rows],
        "cta_%": [_level(r.get("riq_cta")) for r in rows],
        "fallback_free_%": [100.0 if (r.get("fallback") or "").strip() == "N" else 0.0
                            for r in rows],
    }


def llm_by_brief(rows) -> dict:
    """brief -> {'reps', 'mean_pass', 'weakest', 'mix'} for the --llm view.

    weakest is the lowest-mean of hook/challenge/cta by level (ties ->
    riq_hook first); mix is the difficulty counts, most common first."""
    grouped: dict = {}
    for r in rows:
        brief = (r.get("brief") or "").strip() or "?"
        grouped.setdefault(brief, []).append(r)
    out = {}
    for brief, brows in grouped.items():
        counts: dict = {}
        for r in brows:
            diff = (r.get("difficulty") or "").strip() or "?"
            counts[diff] = counts.get(diff, 0) + 1
        means = {c: statistics.fmean(_level(r.get(c)) for r in brows)
                 for c in _RIQ_COLUMNS}
        out[brief] = {
            "reps": len(brows),
            "mean_pass": statistics.fmean(float(r.get("criteria_passed") or 0)
                                          for r in brows),
            "weakest": min(means, key=means.get),
            "mix": "/".join(f"{c}{d[0].upper()}"
                            for d, c in sorted(counts.items(), key=lambda kv: -kv[1])),
        }
    return out


SOURCES = [
    ("full calls", "history.csv", full_series),
    ("objection", "objection_history.csv", objection_series),
    ("star", "star_history.csv", star_series),
    ("narrative", "narrative_history.csv", narrative_series),
    ("drill", "drill_history.csv", drill_series),
    ("llm", LLM_HISTORY, llm_series),
]


def collect(profile: str) -> tuple:
    """(metric -> list of floats in row order, notes with per-source row counts)."""
    series: dict = {}
    notes: list = []
    for label, fname, extract in SOURCES:
        path = SESSIONS / fname
        if fname == LLM_HISTORY:
            rows = _csv_rows(path)  # global funnel: no profile column to filter on
        else:
            rows = _profile_rows(path, profile)
        if not rows:
            notes.append(f"{label}: no rows yet")
            continue
        for k, vals in extract(rows).items():
            series.setdefault(k, []).extend(v for v in vals if v is not None)
    return series, notes


def trend(seq, n: int = 5, tol: float = 0.02) -> str:
    """'improving' / 'declining' / 'plateau' from the last n vs the n before."""
    seq = [x for x in seq if x is not None]
    if len(seq) < 2 * n:
        return "not enough data"
    a, b = statistics.fmean(seq[-2 * n:-n]), statistics.fmean(seq[-n:])
    if abs(b - a) <= max(tol, tol * abs(a)):
        return "plateau"
    return "improving" if b > a else "declining"


def coach(metrics: dict) -> list:
    """Map off-target metrics to the exact drill command. Only acts on metrics
    that are present (not None) so absent sources never trigger a false rep."""
    cmds = []
    g = metrics.get
    if g("opener_latency_s") is not None and g("opener_latency_s") > 1.5:
        cmds.append("--paraphrase --beat opener")
    if g("criteria/5") is not None and g("criteria/5") < 5:
        cmds.append("none - run a full call:  mock_call.py --profile <name>")
    if ((g("reflex_%") is not None and g("reflex_%") < 100) or
            (g("median_onset_s") is not None and g("median_onset_s") > 2.0) or
            (g("obj_ok_fast_%") is not None and g("obj_ok_fast_%") < 100)):
        cmds.append("--objection")
    elif g("ack_rate_%") is not None and g("ack_rate_%") < 100:
        cmds.append("--objection  # acknowledge first in full calls")
    if g("star_solid_%") is not None and g("star_solid_%") < 100:
        cmds.append("--star")
    if g("narrative_airtight_%") is not None and g("narrative_airtight_%") < 100:
        cmds.append("--narrative")
    if ((g("drill_hit_%") is not None and g("drill_hit_%") < 100) or
            (g("cost_fast_%") is not None and g("cost_fast_%") < 100)):
        cmds.append("--drill")
    if g("hook_%") is not None and g("hook_%") < 100:
        cmds.append("--grid  # build the R+I+Q cold")
    if g("challenge_%") is not None and g("challenge_%") < 100:
        cmds.append("--objection --llm  # reflexes")
    if g("cta_%") is not None and g("cta_%") < 100:
        cmds.append("--llm --brief <weakest>  # close with two times")
    if g("filler_rate_per100") is not None and g("filler_rate_per100") > 3:
        cmds.append("--star  # slow down, drop filler")
    return cmds


def _llm_view() -> int:
    """--llm: per-brief breakdown of the global LLM funnel (replaces the standard
    view; nothing is ever written in this mode)."""
    rows = _csv_rows(SESSIONS / LLM_HISTORY)
    if not rows:
        print("No LLM funnel data yet - run mock_call.py --llm for a graded rep. "
              "Nothing written.")
        return 0
    by_brief = llm_by_brief(rows)
    total = sum(v["reps"] for v in by_brief.values())
    w = max([len("brief")] + [len(b) for b in by_brief])
    lines = [f"LLM FUNNEL  per-brief  ({total} reps, global - not profile-filtered)", ""]
    lines.append(f"{'brief':{w}} {'reps':>4} {'crit/5':>6} {'weakest':>14}  mix")
    for brief in sorted(by_brief):
        v = by_brief[brief]
        lines.append(f"{brief:{w}} {v['reps']:>4} {v['mean_pass']:>6.1f} "
                     f"{v['weakest']:>14}  {v['mix']}")
    print("\n".join(lines))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Per-profile progress vs goal + trend + coach")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--n", type=int, default=8, help="rows to average / trend (last N)")
    ap.add_argument("--write", action="store_true", help="also write PROGRESS.md")
    ap.add_argument("--llm", action="store_true",
                    help="per-brief breakdown of the LLM funnel instead of the standard view")
    args = ap.parse_args(argv)
    if args.llm:
        return _llm_view()
    profile = args.profile or profiles.DEFAULT_PROFILE
    n = max(args.n, 1)

    series, notes = collect(profile)
    if not series:
        print(f"No progress data for profile '{profile}' yet. Run sessions/drills or pass "
              f"--profile with data (e.g. --profile procore). Nothing written.")
        return 0

    now = {k: statistics.fmean(seq[-n:]) for k, seq in series.items()}

    lines = [f"PROGRESS  profile={profile}  (now = mean of last {min(n, min(len(s) for s in series.values()))})", ""]
    lines.append(f"{'metric':22} {'now':>7} {'goal':>5}  {'trend':>14}  ok")
    for k in ORDER:
        seq = series.get(k)
        if not seq:
            continue
        goal, shrink = GOALS[k]
        wv = now[k]
        ok = "YES" if (wv <= goal if shrink else wv >= goal) else "NO"
        lines.append(f"{k:22} {wv:>7.1f} {str(goal):>5}  {trend(seq, n=n):>14}  {ok}")

    lines.append("")
    for note in notes:
        lines.append(f"  [no data] {note}")
    if _LLM_METRICS & set(series):
        lines.append("  [note] llm funnel metrics are global - "
                     "llm_history.csv has no profile column")
    lines.append("")

    practices = coach(now)
    lines.append("Practice next:")
    if practices:
        for c in practices:
            lines.append(f"  python mock_call.py {c}")
    else:
        lines.append("  keep doing reps - everything on target")

    report = "\n".join(lines)
    print(report)
    if args.write:
        out = SESSIONS / profile / "PROGRESS.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("```\n" + report + "\n```\n", encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
