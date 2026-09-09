"""Cross-session progression view.

The README promises you can "watch the numbers move across reps the same way
you'd track a funnel", but history.csv is raw rows. This prints a per-session
progression of the headline metrics so the trend is visible at a glance.

    python trend.py
    MOCKCALL_SESSIONS=<dir> python trend.py   # different data dir
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


def tabulate(rows) -> str:
    lines = ["session" + " " * 17 + " ".join(f"{label:>6}" for _, label in HEADLINE)]
    for r in rows:
        args = [_fmt(_parse(k, r.get(k, ""))) for k, _ in HEADLINE]
        lines.append(r.get("session", "?")[:22].ljust(24) + " ".join(f"{a:>6}" for a in args))
    return "\n".join(lines)


def main() -> int:
    path = SESSIONS / "history.csv"
    if not path.exists():
        print(f"No progress file at {path}")
        return 1
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    print(tabulate(rows))
    print("\nColumns: crit=criteria/5, open=opener latency s, obj-p=objection "
          "pause s, ack=ack % , fill=filler/100 words, long=longest turn words, "
          "banned=banned word hits, frz=froze turns, talk=talk time s. '-' = no data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
