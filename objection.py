"""Objection first-15-seconds reflex drill.

Trains the first move after a buyer says no: Voss labeling, Sandler negative
reverse, or feel/felt/found — delivered fast, not a defensive pitch.

    python mock_call.py --objection
    python mock_call.py --objection --text --reps 8
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
Capture = Callable[[], Tuple[str, Optional[float], bool]]
SpeakCue = Callable[[str], None]

BRUSH_OFFS = [
    "Not interested.",
    "We're fine where we are.",
    "I don't have time for this.",
    "Send me an email and I'll take a look.",
]


def objection_cues(rng: random.Random, profile=None) -> List[str]:
    """Objection cues: the profile's real objection pools, shuffled with brush-offs."""
    cues: List[str] = []
    if profile is not None:
        for pool in ("status_quo", "burned"):
            cues += list(profile.objection_pools.get(pool, []))
    cues += BRUSH_OFFS
    rng.shuffle(cues)
    return cues


def run_objection_session(
    reps: int,
    minutes: float,
    seed: Optional[int],
    text_mode: bool,
    capture: Capture,
    now: Callable[[], float] = time.monotonic,
    cues: Optional[List[str]] = None,
    speak_cue: SpeakCue = lambda c: None,
    profile=None,
) -> Tuple[List[grader.ObjectionShot], grader.ObjectionSummary]:
    rng = random.Random(seed)
    lines = list((cues if cues is not None else objection_cues(rng, profile))[:reps])
    start = now()
    budget = minutes * 60.0
    shots: List[grader.ObjectionShot] = []
    for i, cue in enumerate(lines, start=1):
        if i > 1 and (now() - start) >= budget:
            break
        speak_cue(cue)
        text, onset, froze = capture()
        reflex, verdict = grader.score_objection_shot(text, onset, froze)
        shots.append(grader.ObjectionShot(
            index=i, cue=cue, text=text, onset_latency=onset,
            froze=froze, reflex=reflex, verdict=verdict,
        ))
        extra = f"  {onset:.1f}s" if onset is not None else ""
        print(f"  [{i}] {verdict}{extra}")
    return shots, grader.summarize_objection(shots, now() - start, reps)


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
    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "-objection"
    outdir = SESSIONS / profile.name / session_id
    outdir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 72)
    print(f"  OBJECTION REFLEX DRILL  --  {reps} shots or {minutes} min")
    print(f"  Buyer: {profile.buyer_name}. First 15s after 'not interested', open with")
    print("  a label, a negative-reverse, or feel/felt/found. Defending = MISS.")
    print("  Target: reflexive within 2 seconds.")
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
                            max_seconds=8.0)
        transcriber = Transcriber(args.model, beam=1,
                                  initial_prompt=profile.whisper_primer)
        print("  Wear headphones so the mic doesn't pick up his voice.")
        recorder.calibrate()
        transcriber._load()
        pause = np.zeros(int(0.35 * SR), dtype=np.float32)
    print()
    input("  Press ENTER to start... ")
    print()

    def speak_cue(cue: str) -> None:
        print(f"{profile.buyer_name} (PM): {cue}")
        if voice is not None:
            segments.append(voice.say(cue))
            segments.append(pause)

    def capture():
        if text_mode:
            said = input("YOU> ").strip()
            return said, None, not said
        rec = recorder.record_turn()
        segments.append(rec.audio)
        segments.append(pause)
        print("  transcribing...", end="", flush=True)
        said = transcriber.transcribe(rec.audio)
        print("\r" + " " * 20 + "\r", end="")
        print(f"YOU: {said or '[silence]'}")
        return said, rec.onset, rec.froze and not said

    try:
        shots, summary = run_objection_session(
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
        grader.render_objection_markdown(
            summary, shots, session_id, wav_name if not text_mode else ""),
        encoding="utf-8",
    )
    grader.append_objection_history(
        SESSIONS / "objection_history.csv", session_id, shots, summary.elapsed_s)
    print(f"  Report:  {outdir / 'report.md'}")
    print(f"  History: {SESSIONS / 'objection_history.csv'}")
    print()
