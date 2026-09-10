"""Per-profile progress: current level vs goal + trend + what to practice next.

    python progress.py                      # default profile
    python progress.py --profile levitate
    python progress.py --profile levitate --write   # also writes PROGRESS.md
"""
from __future__ import annotations

import csv
import os
import statistics
from pathlib import Path

import trend as _trend  # reuse trend._num / _filler_rate

ROOT = Path(__file__).resolve().parent
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))

_MEAN_METRICS = ("criteria/5", "opener_latency_s", "ack_rate_%",
                 "filler_rate_per100", "median_onset_s", "reflex_%", "star_solid_%",
                 "narrative_airtight_%", "drill_hit_%")


def _csv_rows(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return statistics.fmean(vals) if vals else None


def _median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def aggregate_full(rows):
    return {
        "criteria/5": _mean([_trend._num(r.get("criteria_passed")) for r in rows]),
        "opener_latency_s": _mean([_trend._num(r.get("opener_latency")) for r in rows]),
        "ack_rate_%": _mean([_trend._num(r.get("ack_rate")) for r in rows]),
        "filler_rate_per100": _mean([_trend._filler_rate(r.get("filler_rate")) for r in rows]),
    }


def aggregate_objection(rows):
    onsets = [_trend._num(r.get("onset")) for r in rows if _trend._num(r.get("onset")) is not None]
    return {"reflex_%": _mean([100 if r.get("reflex") == "Y" else 0 for r in rows]),
            "median_onset_s": _median(onsets)}


def aggregate_star(rows):
    return {"star_solid_%": _mean([100 if r.get("ok") == "Y" else 0 for r in rows])}


def aggregate_narrative(rows):
    return {"narrative_airtight_%": _mean([100 if r.get("ok") == "Y" else 0 for r in rows])}


def aggregate_drill(rows):
    return {"drill_hit_%": _mean([100 if r.get("cost_question") == "Y" else 0 for r in rows])}


def trend(seq, n: int = 5, tol: float = 0.02):
    """'improving' / 'declining' / 'plateau' from the last n vs the n before."""
    seq = [x for x in seq if x is not None]
    if len(seq) < 2 * n:
        return "not enough data"
    a, b = statistics.fmean(seq[-2 * n:-n]), statistics.fmean(seq[-n:])
    if abs(b - a) <= max(tol, tol * abs(a)):
        return "plateau"
    return "improving" if b > a else "declining"


def coach(metrics: dict) -> list:
    cmds = []
    if (metrics.get("opener_latency_s") or 0) > 1.5:
        cmds.append("--paraphrase --beat opener")
    if (metrics.get("ack_rate_%") or 100) < 100:
        cmds.append("--objection")
    if (metrics.get("criteria/5") or 5) < 4:
        cmds.append("none - run a full call: mock_call.py")
    if (metrics.get("star_solid_%") or 100) < 100:
        cmds.append("--star")
    if (metrics.get("narrative_airtight_%") or 100) < 100:
        cmds.append("--narrative")
    if (metrics.get("drill_hit_%") or 100) < 100:
        cmds.append("--drill")
    if (metrics.get("filler_rate_per100") or 0) >= 3:
        cmds.append("--objection --star   # slow down, drop filler")
    return cmds


GOALS = {
    "criteria/5": 5, "opener_latency_s": 1.5, "ack_rate_%": 100,
    "filler_rate_per100": 3, "reflex_%": 100, "median_onset_s": 2.0,
    "star_solid_%": 100, "narrative_airtight_%": 100, "drill_hit_%": 100,
}


def _profile_rows(path, profile):
    rows = _csv_rows(path)
    return [r for r in rows if (r.get("profile") or "procore") == profile]


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Per-profile progress vs goal + coach")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--n", type=int, default=10, help="rows to average (last N)")
    ap.add_argument("--write", action="store_true", help="also write PROGRESS.md")
    args = ap.parse_args(argv)
    profile = args.profile or "generic_saas"
    agg = {
        **aggregate_full(_profile_rows(SESSIONS / "history.csv", profile)),
        **aggregate_objection(_profile_rows(SESSIONS / "objection_history.csv", profile)),
        **aggregate_star(_profile_rows(SESSIONS / "star_history.csv", profile)),
        **aggregate_narrative(_profile_rows(SESSIONS / "narrative_history.csv", profile)),
        **aggregate_drill(_profile_rows(SESSIONS / "drill_history.csv", profile)),
    }
    lines = [f"PROGRESS  profile={profile}", ""]
    lines.append(f"{'metric':22} {'now':>8} {'goal':>6}  mg")
    for k, v in agg.items():
        if v is None:
            continue
        goal = GOALS.get(k)
        ok = "YES" if (goal is None or (k in ("opener_latency_s", "filler_rate_per100", "median_onset_s") and v <= goal) or v >= goal) else "NO"
        lines.append(f"{k:22} {round(v, 1):>8} {str(goal):>6}  {ok}")
    lines.append("")
    lines.append("Practice next:")
    for c in coach(agg) or ["everything on target - keep doing reps"]:
        lines.append(f"  python mock_call.py {c}")
    report = "\n".join(lines)
    print(report)
    if args.write:
        out = SESSIONS / profile / "PROGRESS.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("```\n" + report + "\n```\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
