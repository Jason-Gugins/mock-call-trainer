"""Re-score saved sessions with the current grader.

Reads the transcript and timings back out of each `sessions/*/report.md` and runs
them through `grade()` again. Use it after changing the rubric so old reps stay
comparable to new ones, instead of comparing against a scoring bug.

    python regrade.py                 # show old vs new for every saved session
    python regrade.py --write         # also refresh report.md + history.csv
"""

from __future__ import annotations

import argparse
import random
import re
from pathlib import Path
from typing import List, Optional, Tuple

import grader as G
import persona as P

ROOT = Path(__file__).resolve().parent
SESSIONS = ROOT / "sessions"

TURN_RE = re.compile(r"^\*\*YOU:\*\*\s*(.*?)\s*_\((.*?)\)_\s*$", re.MULTILINE)
PM_RE = re.compile(r"^\*\*MIKE \(PM\):\*\*\s*(.*?)\s*$", re.MULTILINE)


def _parse_timing(s: str) -> Tuple[Optional[float], float, List[float], bool]:
    """'first word after 1.7s; 11s; gaps: 2.6s' -> (onset, duration, gaps, froze)."""
    froze = "no speech" in s.lower() or "froze" in s.lower()
    onset = None
    m = re.search(r"first word after ([\d.]+)s", s)
    if m:
        onset = float(m.group(1))
    dur = 0.0
    m = re.search(r";\s*([\d.]+)s", s)
    if m:
        dur = float(m.group(1))
    gaps = [float(g) for g in re.findall(r"([\d.]+)s", s.split("gaps:")[1])] \
        if "gaps:" in s else []
    return onset, dur, gaps, froze


def load_session(report: Path) -> Tuple[List[G.Turn], str, bool, bool]:
    text = report.read_text(encoding="utf-8")

    diff = "normal"
    m = re.search(r"\*\*Difficulty:\*\*\s*(\w+)", text)
    if m:
        diff = m.group(1)

    # These two are persona state, not derivable from the candidate's words.
    pain_revealed = "named a real headache" in text
    meeting_booked = "meeting BOOKED" in text

    # Stage metadata is fixed in order; only the PM's wording is randomized, so
    # any seed gives the right is_objection / expects for turn N.
    stages = P.build_script(diff, random.Random(0))
    pm_lines = PM_RE.findall(text)

    turns: List[G.Turn] = []
    for i, (body, timing) in enumerate(TURN_RE.findall(text)):
        if i >= len(stages):
            break
        st = stages[i]
        onset, dur, gaps, froze = _parse_timing(timing)
        turns.append(G.Turn(
            index=i + 1,
            stage_id=st.id,
            expects=st.expects,
            pm_line=pm_lines[i] if i < len(pm_lines) else "",
            text="" if froze else body.strip(),
            onset_latency=onset,
            duration=dur,
            internal_gaps=gaps,
            is_objection=st.is_objection,
            objection_label=st.objection_label,
            froze=froze,
        ))
    return turns, diff, pain_revealed, meeting_booked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="refresh report.md and rebuild history.csv")
    args = ap.parse_args()

    # Only recorded reps. A --text session has no timings to recover, so
    # re-scoring one would silently drop the audio-based metrics.
    reports = [p for p in sorted(SESSIONS.glob("*/report.md"))
               if (p.parent / "session.wav").exists()]
    if not reports:
        print("No recorded sessions found.")
        return 1

    hist = SESSIONS / "history.csv"
    if args.write and hist.exists():
        hist.unlink()

    print(f"{'session':22} {'old':>6} {'new':>6}  {'old verdict':12} {'new verdict':12} pitch-before-pain")
    print("-" * 96)
    for rep_path in reports:
        old_text = rep_path.read_text(encoding="utf-8")
        m = re.search(r"\*\*Result:\*\*\s*(\d)/5", old_text)
        old_score = m.group(1) if m else "?"
        m = re.search(r"\*\*Verdict:\*\*\s*(\w+(?:\s+\w+)?)", old_text)
        old_verdict = (m.group(1) if m else "?").split("--")[0].strip()

        turns, diff, pain, booked = load_session(rep_path)
        rep = G.grade(turns, diff, pain, booked)
        new_verdict = rep.verdict.split("--")[0].strip()
        pbp = next((l.value for l in rep.leaks if l.key == "pitch_before_pain"), "?")

        flag = "  <-- changed" if new_verdict != old_verdict else ""
        print(f"{rep_path.parent.name:22} {old_score+'/5':>6} {str(rep.passed_count)+'/5':>6}"
              f"  {old_verdict:12} {new_verdict:12} {pbp}{flag}")

        if args.write:
            session_id = rep_path.parent.name
            rep_path.write_text(
                G.render_markdown(rep, session_id, "session.wav"), encoding="utf-8")
            G.append_history(hist, session_id, rep)

    if args.write:
        print("\nReports and history.csv refreshed.")
    else:
        print("\nRun with --write to refresh report.md and history.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
