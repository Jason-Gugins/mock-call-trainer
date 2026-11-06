"""Cross-session progression view.

The README promises you can "watch the numbers move across reps the same way
you'd track a funnel", but history.csv is raw rows. This prints a per-session
progression of the headline metrics so the trend is visible at a glance.

    python trend.py
    MOCKCALL_SESSIONS=<dir> python trend.py   # different data dir

The trailing riq column comes from sessions/llm_history.csv (the LLM funnel,
which has no profile column), aligned by session id; llm-only sessions are
appended with dashes for the offline columns.
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))

HEADLINE = [
    ("criteria_passed", "crit"),
    ("opener_latency", "open"),
    ("objection_pause", "obj-p"),
    ("ack_rate", "ack"),
    ("filler_rate", "fill"),
    ("longest_turn", "long"),
    ("banned_words", "banned"),
    ("freezes", "frz"),
    ("talk_time", "talk"),
    ("riq", "riq"),  # llm_history.csv (global funnel), aligned by session id
]


def _num(raw):
    """'0.2s' -> 0.2, '100%' -> 100, '92 words' -> 92, '4' -> 4, 'none' -> None."""
    raw = (raw or "").strip()
    if raw in ("", "n/a", "none") or raw.lower().startswith("no"):
        return None
    m = re.search(r"\d+(?:\.\d+)?", raw)
    return float(m.group(0)) if m else None


def _filler_rate(raw):
    """history stores '2 in 349 words (0.6/100)' — return the RATE (0.6), not
    the raw count, since the column legend promises filler words per 100."""
    m = re.search(r"\((\d+(?:\.\d+)?)/100\)", (raw or ""))
    if m:
        return float(m.group(1))
    return _num(raw)


def _parse(key, raw):
    if key == "filler_rate":
        return _filler_rate(raw)
    return _num(raw)


def _fmt(v):
    if v is None:
        return "-"
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def llm_riq(path=None) -> dict:
    """session -> criteria_passed from llm_history.csv (the global LLM funnel).
    Rows without a session id or a parsable score are skipped."""
    path = path if path is not None else SESSIONS / "llm_history.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for r in rows:
        sess = (r.get("session") or "").strip()
        crit = _num(r.get("criteria_passed"))
        if sess and crit is not None:
            out[sess] = crit
    return out


def tabulate(rows, llm=None) -> str:
    """llm: session -> criteria_passed from llm_history.csv. Sessions present in
    both CSVs get their riq score inline; llm-only sessions are appended with
    dashes for the offline columns."""
    merged = []
    offline = set()
    for r in rows:
        r = dict(r)
        sess = r.get("session", "?")
        offline.add(sess)
        if llm and sess in llm:
            r["riq"] = str(llm[sess])
        merged.append(r)
    for sess, crit in (llm or {}).items():
        if sess not in offline:
            merged.append({"session": sess, "riq": str(crit)})
    header = "session" + " " * (32 - len("session")) + \
             " ".join(f"{label:>6}" for _, label in HEADLINE)
    lines = [header]
    for r in merged:
        sess = r.get("session", "?")
        prof = r.get("profile", "")
        label = f"{sess}/{prof}" if prof else sess
        args = [_fmt(_parse(k, r.get(k, ""))) for k, _ in HEADLINE]
        lines.append(label[:32].ljust(32) + " ".join(f"{a:>6}" for a in args))
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Per-session progression from history.csv")
    ap.add_argument("--profile", default=None,
                    help="only show one profile's rows (e.g. generic_saas); "
                         "without it, mixed-profile rows are shown with a /profile suffix")
    args = ap.parse_args(argv)
    path = SESSIONS / "history.csv"
    if not path.exists():
        print(f"No progress file at {path}")
        return 1
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if args.profile:
        rows = [r for r in rows if r.get("profile") == args.profile]
    print(tabulate(rows, llm=llm_riq()))
    print("\nColumns: crit=criteria/5, open=opener latency s, obj-p=objection "
          "pause s, ack=ack % , fill=filler/100 words, long=longest turn words, "
          "banned=banned word hits, frz=froze turns, talk=talk time s, "
          "riq=llm funnel criteria/5. '-' = no data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
