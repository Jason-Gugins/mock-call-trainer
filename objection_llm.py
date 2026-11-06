"""LLM objection escalation drill (--objection --llm).

The offline objection drill (objection.py) fires scripted cues; this one keeps
the objections LOCAL and predictable — the brief's objection grid plus the
shared brush-offs, seeded-shuffled, no repeats until the pool cycles — and adds
an LLM buyer for flavor only: after each graded response the buyer reacts in
ONE in-character sentence and sets up the next push, so the pressure escalates
round over round. Grading stays deterministic (grader.score_objection_shot
verbatim, plus ack/question components for history); the LLM never touches the
score.

Degradation contract: any OpenRouterError in the reaction path is a silent
skip — one one-time note, a session flag, and the drill finishes on pure local
objections. It never falls back mid-drill to another brain, and a dead API
never costs a rep.

Loop shape (mirrors objection.run_objection_session's injection style):
  - capture() -> (text, onset, froze) is the whole candidate side. In voice
    mode run_live arms the mic through mock_call.ready_gate() and
    Recorder.record_turn()'s onset latency IS the reflex clock; in --text mode
    the input is graded with onset None (HIT, no clock).
  - react(objection, round) -> str|None is the injected reaction seam; tests
    inject fakes, run_live wires _make_react (provider-aware chat, zai ->
    chat_zai). The live callable carries a .provider attribute so the session
    can stamp each round's brain ("zai"/"openrouter") as actually used; any
    round without a reaction stamps "local".
  - speak_cue(cue) prints + speaks every buyer line (objections AND reaction
    lines), exactly like the offline drill's speak_cue seam.
"""
from __future__ import annotations

import csv
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import grader
import objection
import profiles
import riq_briefs
from openrouter_client import (OpenRouterError, chat, chat_zai,
                               resolved_chat_model, tts)

from objection import BRUSH_OFFS   # noqa: F401 — reused pool, re-exported

ROOT = Path(__file__).resolve().parent
# Overridable so tests can't append to the real sessions/ history.
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))
HISTORY_NAME = "objection_llm_history.csv"

Capture = Callable[[], Tuple[str, Optional[float], bool]]
React = Callable[[str, int], Optional[str]]
SpeakCue = Callable[[str], None]

DEAD_API_NOTE = ("  [buyer] the reaction API is unreachable -- buyer reactions "
                 "are off for the rest of this drill; objections stay local.")
COOLING_MARKER = "  (cooling: capability pitch -- buyer pressure drops)"


@dataclass
class ObjectionLlmShot:
    round: int
    brief: str
    objection: str
    ack: bool
    question: bool
    reflex: bool
    verdict: str
    onset: Optional[float]
    response_text: str
    brain: str = "local"     # "zai" | "openrouter" | "local" — as actually used


OBJECTION_LLM_HISTORY_FIELDS = ["session", "round", "brief", "difficulty",
                                "objection", "ack", "question", "verdict",
                                "onset", "response_text", "brain"]


# --------------------------------------------------------------------------
# The session core (offline-testable: every side effect is injected)
# --------------------------------------------------------------------------

def objection_lines(rng: random.Random, brief, reps: int) -> List[str]:
    """The local objection script: brief.objections + the shared BRUSH_OFFS,
    seeded-shuffled, no repeats within a session. If reps exceed the pool the
    seeded order cycles (it does not reshuffle mid-drill)."""
    pool = [o for o in (getattr(brief, "objections", None) or []) if o]
    pool += [b for b in BRUSH_OFFS if b not in pool]
    order = pool[:]
    rng.shuffle(order)
    return [order[i % len(order)] for i in range(reps)]


def summarize_objection_llm(shots: List[ObjectionLlmShot], elapsed_s: float) -> str:
    def n(verdict: str) -> int:
        return sum(1 for s in shots if s.verdict == verdict)

    hits = sum(1 for s in shots if s.reflex)
    return (f"OBJECTION LLM  {hits}/{len(shots)} reflexive  "
            f"({n('FAST')} FAST, {n('OK')} OK, {n('CUT-IN')} cut-in, "
            f"{n('SLOW')} SLOW, {n('MISS')} MISS)  elapsed {elapsed_s:.0f}s")


def run_objection_llm_session(
    reps: int,
    seed: Optional[int],
    brief,
    difficulty: str,
    capture: Capture,
    now: Callable[[], float] = time.monotonic,
    react: Optional[React] = None,
    profile=None,
    speak_cue: SpeakCue = lambda cue: None,
) -> Tuple[List[ObjectionLlmShot], str]:
    """One round = local objection (printed/spoken via speak_cue) -> the
    candidate responds -> deterministic grade -> optional one-line LLM reaction
    -> cooling marker if the response was a pitch; the next objection proceeds
    regardless. `difficulty` and `profile` are accepted for shape parity with
    the offline drill; grading is deliberately difficulty-independent."""
    rng = random.Random(seed)
    brief_id = getattr(brief, "id", "") or "brief"
    lines = objection_lines(rng, brief, reps)
    provider = getattr(react, "provider", "") if react is not None else ""
    react_dead = False
    noted = False
    start = now()
    shots: List[ObjectionLlmShot] = []
    for i, line in enumerate(lines, start=1):
        speak_cue(line)
        text, onset, froze = capture()
        reflex, verdict = grader.score_objection_shot(text, onset, froze)
        ack = grader.is_acknowledged(text)
        question = grader.has_question(text)
        pitched = grader.mentions_capability(text)

        reaction = None
        if react is not None and not react_dead:
            try:
                reaction = (react(line, i) or "").strip() or None
            except OpenRouterError:
                # Silent skip: park the seam for the rest of the session and
                # print the one-time note. The drill degrades to pure local
                # objections — it never falls back mid-drill.
                react_dead = True
                if not noted:
                    noted = True
                    print(DEAD_API_NOTE)

        shots.append(ObjectionLlmShot(
            round=i, brief=brief_id, objection=line, ack=ack, question=question,
            reflex=reflex, verdict=verdict, onset=onset, response_text=text,
            brain=(provider or "local") if reaction else "local"))

        extra = f"  {onset:.1f}s" if onset is not None else ""
        print(f"  [{i}] {verdict}  ack:{'Y' if ack else 'N'} "
              f"question:{'Y' if question else 'N'}{extra}")
        if reaction:
            speak_cue(reaction)
        if pitched:
            print(COOLING_MARKER)
    return shots, summarize_objection_llm(shots, now() - start)


# --------------------------------------------------------------------------
# History (append-only CSV; header on creation; SESSIONS honors MOCKCALL_SESSIONS)
# --------------------------------------------------------------------------

def append_objection_llm_history(csv_path: Path, session_id: str,
                                 shots: List[ObjectionLlmShot],
                                 difficulty: str = "normal") -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OBJECTION_LLM_HISTORY_FIELDS,
                           extrasaction="ignore")
        if new:
            w.writeheader()
        for s in shots:
            onset = "" if s.onset is None else f"{s.onset:.1f}"
            w.writerow({
                "session": session_id, "round": s.round, "brief": s.brief,
                "difficulty": difficulty, "objection": s.objection,
                "ack": "Y" if s.ack else "N",
                "question": "Y" if s.question else "N",
                "verdict": s.verdict, "onset": onset,
                "response_text": s.response_text, "brain": s.brain,
            })


# --------------------------------------------------------------------------
# Live wiring (voice path; not covered by tests — audio libs + network)
# --------------------------------------------------------------------------

def _react_system_prompt(brief) -> str:
    return (
        f"You are {brief.persona}, {brief.title}: {brief.company_desc} "
        "You are a busy, skeptical buyer being cold-called, and you are hard "
        "to move. Each round you get the brush-off you just gave and the "
        "round number. Reply with ONE short in-character sentence: react to "
        "the caller's answer, then set up your next push, getting slightly "
        "more impatient each round. Plain speech only: one sentence, no stage "
        "directions, no quotation marks, no meta."
    )


def _make_react(brief, provider: str, model_used: str,
                transport: Optional[Callable] = None) -> React:
    """The live LLM-reaction seam: provider-aware chat (zai -> the Z.ai Coding
    Plan endpoint, anything else -> OpenRouter). OpenRouterError is NOT caught
    here — the session's silent-skip net owns it, so this stays a pure seam."""
    system = _react_system_prompt(brief)

    def react(objection: str, rnd: int) -> Optional[str]:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content":
                     f'Your brush-off (round {rnd}): "{objection}"\n'
                     "The caller just answered. React in one sentence, then "
                     "set up your next push."}]
        if provider == "zai":
            line = chat_zai(messages, model=model_used or None,
                            transport=transport)
        else:
            line = chat(messages, model=model_used or None, transport=transport)
        return line.strip() or None

    react.provider = provider        # the session stamps brain from this
    return react


def _speak(text: str, voice, transport: Optional[Callable], warned) -> None:
    """Buyer speech: OpenRouter TTS played aloud; on ANY failure in that path
    the wave-1 SAPI Voice takes over (warned once per session). Mirrors
    llm_call._speak_buyer, kept local because that helper is bound to llm_call's
    LlmCallState. `warned` is a one-element list flag; this drill keeps no
    session mix, so nothing is returned."""
    try:
        import io

        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        import mock_call
        audio = tts(text, transport=transport)
        data, sr = sf.read(io.BytesIO(audio), dtype="float32")
        mono = data.mean(axis=1) if data.ndim > 1 else data
        sd.play(mono, sr)
        sd.wait()
    except Exception:                              # noqa: BLE001
        if not warned[0]:
            warned[0] = True
            print("  [voice] TTS unavailable, using the Windows voice")
        voice.say(text)


def run_live(args, transport: Optional[Callable] = None) -> None:
    profile = profiles.get_profile(
        getattr(args, "profile", None) or profiles.DEFAULT_PROFILE)
    brief = riq_briefs.get_brief(getattr(args, "brief", "") or "A1")
    reps = getattr(args, "reps", None)
    reps = 8 if reps is None else int(reps)
    difficulty = getattr(args, "difficulty", None) or "normal"
    text_mode = bool(getattr(args, "text", False))
    # Buyer-reaction provider: "openrouter" (default) or "zai" (Z.ai Coding
    # Plan — the subscription runs the reactions; TTS still comes from OpenRouter).
    provider = getattr(args, "buyer_provider", "") or "openrouter"
    if provider == "zai":
        model_used = (getattr(args, "llm_model", None)
                      or os.environ.get("ZAI_MODEL") or "glm-5.3-flash")
    else:
        model_used = resolved_chat_model(getattr(args, "llm_model", None))

    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "-objection-llm"

    print()
    print("=" * 72)
    print(f"  OBJECTION ESCALATION DRILL (LLM)  --  {brief.label}  --  "
          f"{reps} objections")
    print(f"  Buyer: {brief.persona}. The objections are local and predictable;")
    print("  the LLM buyer reacts in character and pushes harder each round.")
    print("  Reflex first: a label, a negative reverse, or feel/felt/found.")
    print("  Pitching capability = MISS. Target: reflexive within 2 seconds.")
    print("=" * 72)
    print(f"  Reaction brain: {provider} chat ({model_used}). "
          f"Grading stays deterministic.")
    print()

    voice = None
    recorder = None
    transcriber = None
    if not text_mode:
        import mock_call
        from mock_call import PM_VOICE, Recorder, Transcriber, Voice

        voice = mock_call.Voice(
            rate=profile.difficulty_rates[difficulty], enabled=True,
            voice_name=getattr(args, "voice", "") or profile.tts_voice
            or PM_VOICE)
        recorder = mock_call.Recorder(
            device=getattr(args, "device", None),
            trailing_silence=min(getattr(args, "silence", 3.0), 1.5),
            max_seconds=8.0)
        transcriber = mock_call.Transcriber(
            getattr(args, "model", "base.en"), beam=1,
            initial_prompt=profile.whisper_primer)
        print(f"  Wear headphones so the mic doesn't pick up {brief.persona}'s voice.")

    # Dial gate: reading the setup is free. Calibration + the whisper model
    # load happen after ENTER, so transcription isn't cold on round 1.
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

    warned = [False]

    def speak_cue(cue: str) -> None:
        print(f"{brief.persona} (PM): {cue}")
        if voice is not None:
            _speak(cue, voice, transport, warned)

    def capture():
        if text_mode:
            said = input("YOU> ").strip()
            return said, None, not said
        # The ready gate: thinking time before arming is free — the recorder
        # measures onset from when the mic opens, not from when the buyer
        # finished. (Shared seam with llm_call and the offline drills.)
        mock_call.ready_gate()
        rec = recorder.record_turn()
        print("  transcribing...", end="", flush=True)
        said = transcriber.transcribe(rec.audio)
        print("\r" + " " * 20 + "\r", end="")
        print(f"YOU: {said or '[silence]'}")
        return said, rec.onset, rec.froze and not said

    react = _make_react(brief, provider, model_used, transport)

    try:
        shots, summary = run_objection_llm_session(
            reps=reps, seed=getattr(args, "seed", None), brief=brief,
            difficulty=difficulty, capture=capture, react=react,
            profile=profile, speak_cue=speak_cue)
    except KeyboardInterrupt:
        print("\n  Drill abandoned.\n")
        sys.exit(130)

    print()
    print(f"  {summary}")
    if text_mode:
        print("  (--text mode: reflexes are graded, but timing is not measured)")
    append_objection_llm_history(SESSIONS / HISTORY_NAME, session_id, shots,
                                 difficulty=difficulty)
    print(f"  History: {SESSIONS / HISTORY_NAME}")
    print()
