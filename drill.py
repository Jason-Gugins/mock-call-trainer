"""Pain-reveal drill: skip the full call, fire the broken moment, grade cost+speed."""
from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import grader
import persona
import profiles

ROOT = Path(__file__).resolve().parent
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))
Capture = Callable[[], Tuple[str, Optional[float], bool]]
SpeakCue = Callable[[str], None]


def run_drill_session(
    reps: int,
    minutes: float,
    seed: Optional[int],
    text_mode: bool,
    capture: Capture,
    now: Callable[[], float] = time.monotonic,
    cues: Optional[List[str]] = None,
    speak_cue: SpeakCue = lambda c: None,
    profile=None,
) -> Tuple[List[grader.DrillShot], grader.DrillSummary]:
    rng = random.Random(seed)
    lines = cues if cues is not None else persona.pain_drill_cues(reps, rng, profile)
    start = now()
    budget = minutes * 60.0
    shots: List[grader.DrillShot] = []
    for i, cue in enumerate(lines, start=1):
        if i > 1 and (now() - start) >= budget:
            break
        speak_cue(cue)
        text, onset, froze = capture()
        hit, verdict = grader.score_drill_shot(text, onset, froze)
        shots.append(grader.DrillShot(
            index=i, pm_line=cue, text=text, onset_latency=onset,
            froze=froze, cost_question=hit, verdict=verdict,
        ))
        extra = f"  {onset:.1f}s" if onset is not None else ""
        print(f"  [{i}] {verdict}{extra}")
    elapsed = now() - start
    return shots, grader.summarize_drill(shots, elapsed, reps)


def run_live(args) -> None:
    """Mic or --text entry point. KeyboardInterrupt exits 130."""
    import sys
    from datetime import datetime

    import numpy as np

    from mock_call import SR, Recorder, Transcriber, Voice

    reps = args.reps
    minutes = args.minutes
    text_mode = args.text
    profile = profiles.get_profile(getattr(args, "profile", None) or profiles.DEFAULT_PROFILE)
    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "-drill"
    outdir = SESSIONS / profile.name / session_id
    outdir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 72)
    print(f"  PAIN-REVEAL DRILL  --  {reps} shots or {minutes} min")
    print("  Grade: cost question + speed. Skip opener, objections, close.")
    print("=" * 72)

    voice = None
    recorder = None
    transcriber = None
    segments: list = []
    pause = np.zeros(0, dtype=np.float32)
    if not text_mode:
        voice = Voice(rate=profile.difficulty_rates["normal"], enabled=True)
        recorder = Recorder(
            device=args.device,
            trailing_silence=min(args.silence, 1.5),
            max_seconds=8.0,
        )
        transcriber = Transcriber(args.model, beam=1,
                                  initial_prompt=profile.whisper_primer)
        print("  Wear headphones so the mic doesn't pick up his voice.")
        recorder.calibrate()
        transcriber._load()
        pause = np.zeros(int(0.35 * SR), dtype=np.float32)
    print()
    input("  Press ENTER to start the drill... ")
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
        shots, summary = run_drill_session(
            reps=reps,
            minutes=minutes,
            seed=args.seed,
            text_mode=text_mode,
            capture=capture,
            speak_cue=speak_cue,
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
        grader.render_drill_markdown(
            summary, shots, session_id, wav_name if not text_mode else "",
        ),
        encoding="utf-8",
    )
    grader.append_drill_history(
        SESSIONS / "drill_history.csv", session_id, shots, summary.elapsed_s,
        profile=profile.name,
    )
    print(f"  Report:  {outdir / 'report.md'}")
    print(f"  History: {SESSIONS / 'drill_history.csv'}")
    print()
