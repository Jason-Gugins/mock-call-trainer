"""STAR story drill.

Rehearse behavioural stories until automatic: a specific number and a full
Situation-Task-Action-Result arc, in ~60 seconds. Exactly what the progress
report lists as priority work before deep-stage interviews.

    python mock_call.py --star
    python mock_call.py --star --text --reps 3
"""
from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import grader
import profiles

ROOT = Path(__file__).resolve().parent
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))
# (text, onset, froze, duration_s)
Capture = Callable[[], Tuple[str, Optional[float], bool, Optional[float]]]
SpeakCue = Callable[[str, int], None]


def run_star_session(
    reps: int,
    minutes: float,
    seed: Optional[int],
    text_mode: bool,
    capture: Capture,
    now: Callable[[], float] = time.monotonic,
    topics: Optional[List[str]] = None,
    speak_cue: SpeakCue = lambda t, i: None,
    report=None,
    profile=None,
) -> Tuple[List[grader.StarShot], grader.StarSummary]:
    topics = topics if topics is not None else (
        list(profile.star_stories) if profile is not None else [])
    if not topics:
        topics = ["Untitled story"]
    start = now()
    budget = minutes * 60.0
    shots: List[grader.StarShot] = []
    for i in range(1, reps + 1):
        if i > 1 and (now() - start) >= budget:
            break
        topic = topics[(i - 1) % len(topics)]
        speak_cue(topic, i)
        text, _onset, _froze, duration = capture()
        missing = grader.score_star_shot(text, duration)
        shots.append(grader.StarShot(
            index=i, topic=topic, text=text, duration=duration, missing=missing))
        label = "SOLID" if not missing else "WEAK: " + "; ".join(missing)
        print(f"  [{i}] {label}")
        if report is not None:
            report(shots[-1])
    return shots, grader.summarize_star(shots, now() - start, reps)


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
    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "-star"
    outdir = SESSIONS / profile.name / session_id
    outdir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 72)
    print(f"  STAR STORY DRILL  --  {reps} stories or {minutes} min")
    print("  Each story needs a Situation, Task, Action, Result, and a specific number.")
    print("  Aim for ~60 seconds (45-90). Rehearse until it's automatic.")
    print("=" * 72)
    for i, t in enumerate(profile.star_stories, start=1):
        print(f"    {i}. {t}")
    print()

    voice = None
    recorder = None
    transcriber = None
    segments: list = []
    pause = np.zeros(0, dtype=np.float32)
    if not text_mode:
        voice = Voice(rate=profile.difficulty_rates["normal"], enabled=True)
        recorder = Recorder(device=args.device,
                            trailing_silence=min(args.silence, 1.5),
                            max_seconds=150.0)
        transcriber = Transcriber(args.model, beam=1,
                                  initial_prompt=profile.whisper_primer)
        print("  Wear headphones so the mic doesn't pick up his voice.")
        recorder.calibrate()
        transcriber._load()
        pause = np.zeros(int(0.35 * SR), dtype=np.float32)
    print()
    input("  Press ENTER to start... ")
    print()

    def speak_cue(topic: str, i: int) -> None:
        print(f"--- story {i} / {reps}: {topic} ---")
        print(f"{profile.buyer_name} (PM): Tell me about a time...")
        if voice is not None:
            segments.append(voice.say(f"Tell me about a time related to {topic}."))
            segments.append(pause)

    def capture():
        if text_mode:
            print(f"YOU> ", end="", flush=True)
            said = input()
            return said.strip(), None, not said, None
        rec = recorder.record_turn()
        segments.append(rec.audio)
        segments.append(pause)
        print("  transcribing...", end="", flush=True)
        said = transcriber.transcribe(rec.audio)
        print("\r" + " " * 20 + "\r", end="")
        print(f"YOU: {said or '[silence]'}")
        return said, rec.onset, rec.froze and not said, rec.duration

    try:
        shots, summary = run_star_session(
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
        grader.render_star_markdown(
            summary, shots, session_id, wav_name if not text_mode else ""),
        encoding="utf-8",
    )
    grader.append_star_history(
        SESSIONS / "star_history.csv", session_id, shots, summary.elapsed_s)
    print(f"  Report:  {outdir / 'report.md'}")
    print(f"  History: {SESSIONS / 'star_history.csv'}")
    print()
