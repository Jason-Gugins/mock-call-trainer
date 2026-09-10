"""Career narrative + gap-answer drill.

Rehearse the three questions that decide every deep-stage round: why sales,
why this company, and a confident one-line answer to the 2018-2023 gap that
pivots forward. Graded on evidence, concision, and no hedging.

    python mock_call.py --narrative
    python mock_call.py --narrative --text --reps 3
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import grader
import profiles

ROOT = Path(__file__).resolve().parent
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))
Capture = Callable[[], Tuple[str, Optional[float], bool]]
SpeakCue = Callable[[str, int], None]

KINDS = ["why_sales", "why_company", "gap"]


def run_narrative_session(
    reps: int,
    minutes: float,
    seed: Optional[int],
    text_mode: bool,
    capture: Capture,
    now: Callable[[], float] = time.monotonic,
    kinds: Optional[List[str]] = None,
    speak_cue: SpeakCue = lambda label, i: None,
    profile=None,
) -> Tuple[List[grader.NarrativeShot], grader.NarrativeSummary]:
    kinds = kinds or KINDS
    start = now()
    budget = minutes * 60.0
    shots: List[grader.NarrativeShot] = []
    for i in range(1, reps + 1):
        if i > 1 and (now() - start) >= budget:
            break
        kind = kinds[(i - 1) % len(kinds)]
        label = grader.NARRATIVE_LABELS[kind]
        speak_cue(label, i)
        text, _onset, _froze = capture()
        missing = grader.score_narrative_shot(kind, text)
        shots.append(grader.NarrativeShot(
            index=i, kind=kind, label=label, text=text, missing=missing))
        status = "AIR-TIGHT" if not missing else "; ".join(missing)
        print(f"  [{i}] {status}")
    return shots, grader.summarize_narrative(shots, now() - start, reps)


def run_live(args) -> None:
    import sys
    from datetime import datetime

    import numpy as np

    from mock_call import SR, Recorder, Transcriber, Voice

    profile = profiles.get_profile(
        getattr(args, "profile", None) or profiles.DEFAULT_PROFILE)
    reps = args.reps
    minutes = args.minutes
    text_mode = args.text
    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "-narrative"
    outdir = SESSIONS / profile.name / session_id
    outdir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 72)
    print(f"  CAREER NARRATIVE DRILL  --  {reps} answers or {minutes} min")
    print("  One confident sentence, a real detail, no hedging.")
    print("=" * 72)

    voice = None
    recorder = None
    transcriber = None
    segments: list = []
    pause = np.zeros(0, dtype=np.float32)
    if not text_mode:
        voice = Voice(rate=profile.difficulty_rates["normal"], enabled=True)
        recorder = Recorder(device=args.device,
                            trailing_silence=min(args.silence, 1.5),
                            max_seconds=30.0)
        transcriber = Transcriber(args.model, beam=1,
                                  initial_prompt=profile.whisper_primer)
        print("  Wear headphones so the mic doesn't pick up his voice.")
        recorder.calibrate()
        transcriber._load()
        pause = np.zeros(int(0.35 * SR), dtype=np.float32)
    print()
    input("  Press ENTER to start... ")
    print()

    def speak_cue(label: str, i: int) -> None:
        print(f"--- answer {i} / {reps}: {label} ---")
        if voice is not None:
            segments.append(voice.say(label))
            segments.append(pause)

    def capture():
        if text_mode:
            print("YOU> ", end="", flush=True)
            said = input()
            return said.strip(), None, not said
        rec = recorder.record_turn()
        segments.append(rec.audio)
        segments.append(pause)
        print("  transcribing...", end="", flush=True)
        said = transcriber.transcribe(rec.audio)
        print("\r" + " " * 20 + "\r", end="")
        print(f"YOU: {said or '[silence]'}")
        return said, rec.onset, rec.froze and not said

    try:
        shots, summary = run_narrative_session(
            reps=reps, minutes=minutes, seed=args.seed,
            text_mode=text_mode, capture=capture, speak_cue=speak_cue,
            profile=profile,
        )
    except KeyboardInterrupt:
        print("\n  Drill abandoned.\n")
        sys.exit(130)

    print()
    print(summary.line)
    print(f"  Elapsed: {summary.elapsed_s:.0f}s of {minutes * 60:.0f}s budget")
    print()

    wav_name = "session.wav"
    if not text_mode:
        import soundfile as sf
        full = np.concatenate([s for s in segments if s.size]) if segments else np.zeros(1)
        peak = float(np.max(np.abs(full))) or 1.0
        sf.write(str(outdir / wav_name), (full / peak * 0.95).astype(np.float32), SR)
        print(f"  Audio:   {outdir / wav_name}")

    (outdir / "report.md").write_text(
        grader.render_narrative_markdown(
            summary, shots, session_id, wav_name if not text_mode else ""),
        encoding="utf-8",
    )
    grader.append_narrative_history(
        SESSIONS / "narrative_history.csv", session_id, shots)
    print(f"  Report:  {outdir / 'report.md'}")
    print(f"  History: {SESSIONS / 'narrative_history.csv'}")
    print()
