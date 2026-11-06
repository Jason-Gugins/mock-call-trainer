"""120-second RIQ prep-grid drill (--grid flag; wired into mock_call.py later).

One rep: a REDACTED brief card — persona, title, company_desc (their world)
and internal_signal (the signal you can see) — hits the screen, and the prep
clock starts. challenge_hint is withheld because that IS the answer, and the
external_trigger text is withheld because building R (the industry pressure)
from the card is the skill. At the shared ready gate you arm the mic and
deliver opener + hook + challenge question in ONE turn; a deterministic
six-element structure grade follows, then the verdict line and the next rep.

The six elements (grid_score):
  opener     permissive interruption (the generic_saas opener beat)
  hook_r     an R term from the brief's riq_terms["R"] regex bank
  hook_i     an I term from the brief's riq_terms["I"] regex bank
  challenge  riq_grade.RIQ_CHALLENGE_RE shape OR an implication question
  question   the delivery ENDS on a question
  no_pitch   no capability pitch (grader.PITCH_MARKERS)
Banned-phrase hits (grader.BANNED_PHRASES) are reported alongside but never
flip no_pitch. Prep time is graded FAST <= 60s / OK <= 120s / SLOW — SLOW
never hard-fails a rep; the structure grade is the pass.

Loop shape (mirrors drill.run_drill_session / objection_llm): capture() ->
(text, prep_s, duration_s, froze) is the whole candidate side and is injected;
tests inject fakes, run_live wires Recorder + Transcriber + the ready gate.
`froze` is accepted for seam parity — a frozen delivery already grades 0/6 on
its empty text. text_mode and profile are accepted for shape parity with the
live wiring; grading depends only on what capture returns.

Artifact: sessions/grid_history.csv (append-only, header on creation) plus the
console. No report.md on purpose — history + console is the artifact.
"""
from __future__ import annotations

import csv
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import grader
import profiles
import riq_briefs
import riq_grade

ROOT = Path(__file__).resolve().parent
# Overridable so tests can't append to the real sessions/ history.
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))
GRID_HISTORY_NAME = "grid_history.csv"
GRID_HISTORY_FIELDS = ["session", "rep", "brief", "prep_s", "passes",
                       "opener", "hook_r", "hook_i", "challenge", "question",
                       "no_pitch", "banned", "duration", "text"]

# capture() -> (text, prep_s, duration_s, froze) is the whole candidate side.
Capture = Callable[[], Tuple[str, Optional[float], Optional[float], bool]]
Now = Callable[[], float]

PREP_FAST_S = 60.0
PREP_OK_S = 120.0

ELEMENT_KEYS = ["opener", "hook_r", "hook_i", "challenge", "question",
                "no_pitch"]

INSTRUCTION_LINE = ("Build R (an industry pressure) + I (their signal) into a "
                    "challenge question. You have 120 seconds.")


class RepSetDone(Exception):
    """Raised by the text-mode capture when the input pipe runs dry
    (EOFError): ends the rep set gracefully, keeping every shot so far."""


@dataclass
class GridShot:
    index: int
    brief_id: str
    prep_s: Optional[float]
    passes: int
    elements: Dict[str, bool]
    banned: List[str]
    duration_s: Optional[float]
    text: str
    verdict: str          # prep verdict: FAST | OK | SLOW


# --------------------------------------------------------------------------
# The pure grader
# --------------------------------------------------------------------------

def grid_score(text: str, brief) -> Tuple[int, Dict[str, bool]]:
    """Deterministic six-element structure grade. Returns (passes, elements)
    where passes is the count of elements hit (0..6). Banned phrases are not
    part of the grade — the session reports them alongside."""
    t = (text or "").lower()
    sents = grader.sentences(text or "")
    elements = {
        "opener": profiles.get_profile("generic_saas").beats["opener"]
                  .check_idea(text or "")[0],
        "hook_r": any(re.search(p, t) for p in brief.riq_terms.get("R", [])),
        "hook_i": any(re.search(p, t) for p in brief.riq_terms.get("I", [])),
        "challenge": bool(re.search(riq_grade.RIQ_CHALLENGE_RE, t))
                     or grader.has_implication_question(text or ""),
        "question": bool(sents) and grader.is_question(sents[-1]),
        "no_pitch": not grader.mentions_capability(text or ""),
    }
    return sum(elements.values()), elements


def redacted_card(brief) -> str:
    """The prep card: the four allowed fields, clearly labeled, plus the
    instruction. challenge_hint (the answer) and external_trigger (building R
    is the skill) are redacted on purpose."""
    return (
        f"  PERSONA: {brief.persona}\n"
        f"  TITLE:   {brief.title}\n"
        f"  THEIR WORLD: {brief.company_desc}\n"
        f"  SIGNAL YOU CAN SEE: {brief.internal_signal}\n"
        f"\n  {INSTRUCTION_LINE}"
    )


def prep_verdict(prep_s: Optional[float]) -> str:
    """FAST <= 60s / OK <= 120s / SLOW beyond. A missing clock (text mode)
    grades OK — prep never hard-fails a rep."""
    if prep_s is None:
        return "OK"
    if prep_s <= PREP_FAST_S:
        return "FAST"
    if prep_s <= PREP_OK_S:
        return "OK"
    return "SLOW"


# --------------------------------------------------------------------------
# The session core (offline-testable: every side effect is injected)
# --------------------------------------------------------------------------

def _print_shot(shot: GridShot) -> None:
    prep = f"{shot.prep_s:.0f}s" if shot.prep_s is not None else "untimed"
    built = shot.passes == len(shot.elements)
    print(f"  [{shot.index}] {shot.brief_id}  "
          f"{'BUILT' if built else 'MISS'} {shot.passes}/{len(shot.elements)}"
          f"  prep {shot.verdict} {prep}")
    missing = [k for k, v in shot.elements.items() if not v]
    if missing:
        print(f"      missing: {', '.join(missing)}")
    if shot.banned:
        print(f"      banned words: {', '.join(shot.banned)}")


def summarize_grid(shots: List[GridShot], elapsed_s: float,
                   reps_requested: Optional[int] = None,
                   ended_early: bool = False) -> str:
    built = sum(1 for s in shots if s.passes == len(s.elements))

    def n(verdict: str) -> int:
        return sum(1 for s in shots if s.verdict == verdict)

    line = (f"GRID  {built}/{len(shots)} built  "
            f"(prep {n('FAST')} FAST / {n('OK')} OK / {n('SLOW')} SLOW)  "
            f"elapsed {elapsed_s:.0f}s")
    if ended_early and reps_requested and len(shots) < reps_requested:
        line += f"  ended early at {len(shots)}/{reps_requested}"
    return line


def run_grid_session(
    reps: int,
    seed: Optional[int],
    brief_id: str,
    text_mode: bool,
    capture: Capture,
    now: Now = time.monotonic,
    profile=None,
) -> Tuple[List[GridShot], str]:
    """One rep: the redacted card prints -> capture() hands back the delivery
    with its prep clock -> six-element grade -> verdict line -> next rep.

    Brief selection: pinned brief_id, else a seeded shuffle of
    riq_briefs.BRIEFS (no repeats until the pool cycles). text_mode and
    profile are accepted for shape parity with the live wiring; grading
    depends only on what capture returns. RepSetDone from the capture ends
    the set gracefully. Returns (shots, summary line)."""
    rng = random.Random(seed)
    if brief_id:
        pinned = riq_briefs.get_brief(brief_id)
        briefs = [pinned] * reps
    else:
        order = list(riq_briefs.BRIEFS)
        rng.shuffle(order)
        briefs = [order[i % len(order)] for i in range(reps)]

    start = now()
    shots: List[GridShot] = []
    ended_early = False
    for i, brief in enumerate(briefs, start=1):
        print()
        print(f"  REP {i}/{reps}")
        print(redacted_card(brief))
        try:
            text, prep_s, duration_s, _froze = capture()
        except RepSetDone:
            ended_early = True
            break
        passes, elements = grid_score(text, brief)
        shot = GridShot(
            index=i, brief_id=brief.id, prep_s=prep_s, passes=passes,
            elements=elements,
            banned=grader.find_matches(text or "", grader.BANNED_PHRASES),
            duration_s=duration_s, text=text, verdict=prep_verdict(prep_s))
        shots.append(shot)
        _print_shot(shot)
    return shots, summarize_grid(shots, now() - start, reps, ended_early)


# --------------------------------------------------------------------------
# History (append-only CSV; header on creation; SESSIONS honors MOCKCALL_SESSIONS)
# --------------------------------------------------------------------------

def append_grid_history(csv_path: Path, session_id: str,
                        shots: List[GridShot]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=GRID_HISTORY_FIELDS,
                           extrasaction="ignore")
        if new:
            w.writeheader()
        for s in shots:
            w.writerow({
                "session": session_id, "rep": s.index, "brief": s.brief_id,
                "prep_s": "" if s.prep_s is None else f"{s.prep_s:.1f}",
                "passes": s.passes,
                "opener": "Y" if s.elements.get("opener") else "N",
                "hook_r": "Y" if s.elements.get("hook_r") else "N",
                "hook_i": "Y" if s.elements.get("hook_i") else "N",
                "challenge": "Y" if s.elements.get("challenge") else "N",
                "question": "Y" if s.elements.get("question") else "N",
                "no_pitch": "Y" if s.elements.get("no_pitch") else "N",
                "banned": "|".join(s.banned),
                "duration": ("" if s.duration_s is None
                             else f"{s.duration_s:.1f}"),
                "text": s.text,
            })


# --------------------------------------------------------------------------
# Live wiring (voice path; not covered by tests — audio libs + mic)
# --------------------------------------------------------------------------

def run_live(args) -> None:
    """Mic or --text entry point. KeyboardInterrupt exits 130."""
    profile = profiles.get_profile(
        getattr(args, "profile", None) or profiles.DEFAULT_PROFILE)
    reps = getattr(args, "reps", None)
    reps = 3 if reps is None else int(reps)
    text_mode = bool(getattr(args, "text", False))
    brief_id = getattr(args, "brief", None) or ""
    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "-grid"

    print()
    print("=" * 72)
    print(f"  RIQ PREP GRID  --  {reps} reps  --  120 seconds of prep each")
    print("  The card shows their world and the signal you can see. The "
          "external trigger")
    print("  stays hidden: building R (the industry pressure) is the skill.")
    print("  Deliver opener + hook + challenge question in ONE turn. No pitch.")
    print("=" * 72)

    recorder = None
    transcriber = None
    if not text_mode:
        import mock_call
        from mock_call import Recorder, Transcriber

        recorder = Recorder(
            device=getattr(args, "device", None),
            trailing_silence=min(getattr(args, "silence", 3.0), 2.5),
            max_seconds=45.0)
        transcriber = Transcriber(
            getattr(args, "model", "base.en"), beam=1,
            initial_prompt=profile.whisper_primer)
        print("  One turn per rep: the mic opens when you arm it at the gate.")

    # Dial gate: reading the setup is free. Calibration + the whisper model
    # load happen after ENTER, so transcription isn't cold on rep 1.
    try:
        input("  Press ENTER to start... ")
    except KeyboardInterrupt:
        print("\n\n  Drill abandoned before it started.\n")
        sys.exit(130)
    except EOFError:
        print("\n\n  No input (dry pipe). Drill never started.\n")
        sys.exit(130)
    if not text_mode:
        recorder.calibrate()
        transcriber._load()
    print()

    def capture():
        if text_mode:
            try:
                said = input("YOU> ").strip()
            except EOFError:
                print()
                raise RepSetDone from None
            return said, None, None, False
        # Prep clock: card -> armed at the gate (the shared seam with llm_call
        # and the other drills). Thinking past 120s grades SLOW, never a fail.
        t0 = time.monotonic()
        mock_call.ready_gate()
        prep_s = time.monotonic() - t0
        rec = recorder.record_turn()
        print("  transcribing...", end="", flush=True)
        said = transcriber.transcribe(rec.audio)
        print("\r" + " " * 20 + "\r", end="")
        print(f"YOU: {said or '[silence]'}")
        return said, prep_s, rec.duration, rec.froze and not said

    try:
        shots, summary = run_grid_session(
            reps=reps, seed=getattr(args, "seed", None), brief_id=brief_id,
            text_mode=text_mode, capture=capture, profile=profile)
    except KeyboardInterrupt:
        print("\n  Drill abandoned.\n")
        sys.exit(130)

    print()
    print(f"  {summary}")
    if text_mode:
        print("  (--text mode: structure is graded, but prep is not timed)")
    append_grid_history(SESSIONS / GRID_HISTORY_NAME, session_id, shots)
    print(f"  History: {SESSIONS / GRID_HISTORY_NAME}")
    print()
