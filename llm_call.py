"""LLM cold call mode (--llm): the buyer is played by an OpenRouter chat model.

The candidate gets the persona brief at dial time (the 120-second prep grid),
then speaks into the mic exactly like the offline trainer. The buyer brain is
RIQ-master-prompted; grading stays deterministic (riq_grade). Any API failure
mid-call falls back to the offline scripted persona and the report is stamped
FALLBACK — a rep is never lost to the network.

Loop shape (the implementation contract):
  - The pickup comes from the LLM: the first buyer request carries
    build_turn_message("", warmth, 1, max_turns). The loop's REAL turn number
    goes into every build_turn_message call (never turn+1: it would let the
    counter exceed the cap the system prompt promises).
  - next_buyer_line returns the RAW model text. is_hangup is checked on the
    raw reply BEFORE anything is spoken, displayed, or graded — checking after
    strip_meta is the classic bug (a compliant lone [[HANGUP]] deletes itself).
    A hangup reply ENDS THE CALL (break), wherever it lands — including an
    instant hangup at pickup (zero turns, report still written). Winding down
    at the cap or a dry pipe are the only other endings.
  - recorder.record_turn() returns a mock_call.Recording (audio, onset,
    duration, gaps, froze); the grader.Turn is built FROM it
    (onset_latency=recording.onset, internal_gaps=recording.gaps,
    froze=recording.froze and not said). Segment bookkeeping mirrors
    mock_call.run_call exactly: 0.35 s pauses, and turn_starts.append before
    each turn's audio so both sides land in session.wav/session.html.
  - Buyer speech: OpenRouter TTS (mp3, 24 kHz mono) played and resampled into
    the 16 kHz mix; on ANY failure the wave-1 SAPI Voice takes over (warned
    once per session). Audio lands in the recording either way.
  - Crash safety mirrors mock_call.run_call: EOFError -> persist PARTIAL and
    return; any other BaseException -> persist PARTIAL and re-raise; _persist
    is idempotent via a persisted flag.
"""
from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

import grader
import persona
import profiles
import riq_briefs
import riq_grade
import riq_prompts
from openrouter_client import (OpenRouterError, chat, chat_zai,
                               resolved_chat_model, tts)

import mock_call

ROOT = Path(__file__).resolve().parent
# Overridable so tests can't append to the real sessions/ or llm_history.csv.
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))
DEFAULT_CALLER_COMPANY = "AudienceView"
HISTORY_NAME = "llm_history.csv"     # history.csv (offline funnel) is never touched


@dataclass
class LlmCallState:
    """What a rep accumulates, plus the idempotence + fallback bookkeeping."""
    segments: List[np.ndarray] = field(default_factory=list)
    turns: List[grader.Turn] = field(default_factory=list)
    turn_starts: List[float] = field(default_factory=list)
    partial: bool = False
    persisted: bool = False            # _persist runs at most once per rep
    fallback: bool = False             # buyer API died -> scripted persona
    model: str = ""
    script: List = field(default_factory=list)   # persona.Stage list (fallback)
    script_i: int = 0
    tts_warned: bool = False           # the SAPI warning prints once per rep


# --------------------------------------------------------------------------
# Buyer side
# --------------------------------------------------------------------------

def _scripted_line(state: LlmCallState) -> str:
    """Next line from the offline persona script, clamped at the last stage."""
    if not state.script:
        return ""
    stage = state.script[min(state.script_i, len(state.script) - 1)]
    state.script_i += 1
    return stage.line(True)


def _next_buyer_line(state: LlmCallState, messages: List[Dict],
                     candidate_text: str, warmth: int, turn: int, max_turns: int,
                     difficulty: str, script_rng: random.Random, profile,
                     model: str, transport: Optional[Callable],
                     provider: str = "openrouter") -> str:
    """The buyer's next line — the RAW model text (any [[HANGUP]] meta still
    inside; the caller checks is_hangup BEFORE stripping or speaking).

    provider: "openrouter" (default) or "zai" — the Z.ai Coding Plan endpoint
    runs the buyer brain on the subscription instead of OpenRouter credits.
    Only the chat call is API-bound. On OpenRouterError: one warning, the
    offline scripted persona takes over for the rest of the call (not the
    brief's character), and the report is stamped FALLBACK."""
    if state.fallback:
        return _scripted_line(state)
    messages.append({"role": "user", "content": riq_prompts.build_turn_message(
        candidate_text, warmth, turn, max_turns)})
    try:
        if provider == "zai":
            raw = chat_zai(messages, model=model or None, transport=transport)
        else:
            raw = chat(messages, model=model or None, transport=transport)
    except OpenRouterError:
        state.fallback = True
        state.script = persona.build_script(difficulty, script_rng, profile)
        print("  [buyer] the buyer API is unreachable -- the scripted offline "
              "persona finishes this call (not the brief's character). "
              "The rep still grades against the brief.")
        return _scripted_line(state)
    messages.append({"role": "assistant", "content": raw})
    return raw


def _speak_buyer(text: str, voice: "mock_call.Voice",
                 transport: Optional[Callable], state: LlmCallState) -> np.ndarray:
    """Buyer speech: OpenRouter TTS (mp3 in, 24 kHz mono) played aloud and
    resampled into the 16 kHz session mix. ANY failure in that path falls back
    to the wave-1 SAPI Voice (warned once per session). Buyer audio lands in
    the session recording either way."""
    try:
        import io
        import sounddevice as sd
        import soundfile as sf
        audio = tts(text, transport=transport)
        data, sr = sf.read(io.BytesIO(audio), dtype="float32")
        mono = data.mean(axis=1) if data.ndim > 1 else data
        sd.play(mono, sr)
        sd.wait()
        return mock_call._resample(np.asarray(mono, dtype=np.float32),
                                   int(sr), mock_call.SR)
    except Exception:                              # noqa: BLE001
        if not state.tts_warned:
            state.tts_warned = True
            print("  [voice] TTS unavailable, using the Windows voice")
        return voice.say(text)


# --------------------------------------------------------------------------
# Persistence (mirrors mock_call._persist: idempotent, partial-aware)
# --------------------------------------------------------------------------

def _persist(outdir: Path, session_id: str, state: LlmCallState, brief,
             args, text_mode: bool) -> None:
    # Idempotent: the EOF/exception nets and the normal exit all funnel here;
    # a second run would duplicate the llm_history.csv row and re-print the
    # scorecard. The session dir is created lazily so an abandoned-before-dial
    # Ctrl+C leaves no empty folder behind.
    if state.persisted:
        return
    outdir.mkdir(parents=True, exist_ok=True)
    report = riq_grade.grade_riq(state.turns, brief, difficulty=args.difficulty,
                                 model=state.model, fallback=state.fallback)
    report.turn_starts = list(state.turn_starts)
    if state.partial:
        report.verdict = (f"PARTIAL -- call aborted after {len(state.turns)} "
                          f"turn(s). " + report.verdict)
    print(riq_grade.render_console(report))

    wrote_audio = False
    if not text_mode:
        parts = [s for s in state.segments if s.size]
        if parts:                      # fixes np.concatenate([]) ValueError
            import io
            import listenback
            import soundfile as sf
            full = np.concatenate(parts)
            peak = float(np.max(np.abs(full))) or 1.0
            sf.write(str(outdir / "session.wav"),
                     (full / peak * 0.95).astype(np.float32), mock_call.SR)

            # Single-file HTML listen-back: same audio as 16-bit PCM so the
            # base64 embed stays a sane size. RiqReport carries every
            # attribute render() touches (profile/difficulty/score_line/
            # verdict/turns/turn_starts/buyer); turn_starts is empty in text
            # mode and zip truncates safely.
            buf = io.BytesIO()
            sf.write(buf, (full / peak * 0.95 * 32767).astype(np.int16),
                     mock_call.SR, format="WAV", subtype="PCM_16")
            (outdir / "session.html").write_text(
                listenback.render(session_id, report, buf.getvalue()),
                encoding="utf-8")
            wrote_audio = True

    (outdir / "report.md").write_text(
        riq_grade.render_markdown(report, session_id,
                                  "session.wav" if wrote_audio else ""),
        encoding="utf-8")
    riq_grade.append_llm_history(SESSIONS / HISTORY_NAME, session_id, report,
                                 brief_id=brief.id, model=state.model,
                                 difficulty=args.difficulty)

    # Only name the artifacts that were actually written.
    print(f"\n  Report:  {outdir / 'report.md'}")
    if wrote_audio:
        print(f"  Audio:   {outdir / 'session.wav'}")
        print(f"  Listen:  {outdir / 'session.html'}")
    print(f"  History: {SESSIONS / HISTORY_NAME}\n")
    state.persisted = True


# --------------------------------------------------------------------------
# The call
# --------------------------------------------------------------------------

def _ready_gate() -> None:
    """Block until the caller arms the mic: any keypress on Windows (msvcrt),
    ENTER elsewhere. Thinking time before arming is free — the recorder only
    measures onset from when the mic actually opens."""
    if sys.platform == "win32":
        try:
            import msvcrt
            print("  [press any key when you're ready — the mic opens on "
                  "keypress]", end="", flush=True)
            key = msvcrt.getch()
            if key in (b"\x00", b"\xe0"):
                msvcrt.getch()                 # arrow/function keys send a 2nd byte
            if key == b"\x03":                     # Ctrl+C
                raise KeyboardInterrupt
            print("\r" + " " * 64 + "\r", end="")
            return
        except ImportError:
            pass
    input("  [press ENTER when you're ready — the mic opens on keypress] ")


def run_llm_call(args, transport: Optional[Callable] = None) -> None:
    brief = riq_briefs.get_brief(args.brief)   # unknown brief -> clean KeyError
    max_turns = int(getattr(args, "max_turns", 0) or 16)   # never args.reps
    difficulty = args.difficulty
    script_rng = random.Random(args.seed)
    profile = profiles.get_profile(getattr(args, "profile", "")
                                   or profiles.DEFAULT_PROFILE)
    text_mode = bool(args.text)

    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    outdir = SESSIONS / "llm" / session_id

    # Buyer brain provider: "openrouter" (default) or "zai" (Z.ai Coding Plan
    # — the subscription runs the buyer brain; TTS still comes from OpenRouter).
    provider = getattr(args, "buyer_provider", "") or "openrouter"
    if provider == "zai":
        model_used = (getattr(args, "llm_model", None)
                      or os.environ.get("ZAI_MODEL") or "glm-5.3-flash")
    else:
        model_used = resolved_chat_model(getattr(args, "llm_model", None))
    print()
    print("=" * 72)
    print(f"  RIQ LLM COLD CALL  --  brief {brief.id}  --  {difficulty.upper()}")
    print("=" * 72)
    # The candidate sees the brief at dial time, like the real interview's
    # 120-second prep grid.
    print(riq_prompts.brief_card(brief))
    print(f"  Buyer brain: {provider} chat ({model_used}), "
          f"at most {max_turns} buyer replies. Grading stays deterministic.")
    print("=" * 72)
    print()

    voice = None
    recorder = None
    transcriber = None
    if not text_mode:
        voice = mock_call.Voice(
            rate=profile.difficulty_rates[difficulty], enabled=True,
            voice_name=getattr(args, "voice", "") or profile.tts_voice
            or mock_call.PM_VOICE)
        recorder = mock_call.Recorder(device=args.device,
                                      trailing_silence=getattr(args, "silence", 3.0))
        transcriber = mock_call.Transcriber(
            args.model, beam=1 if args.fast else 5,
            initial_prompt=profile.whisper_primer)

    state = LlmCallState(model=model_used)
    messages: List[Dict] = [{"role": "system", "content": riq_prompts.build_system_prompt(
        brief, difficulty=difficulty, caller_company=DEFAULT_CALLER_COMPANY,
        max_turns=max_turns)}]
    warmth = grader.WARMTH_START
    pause = np.zeros(int(0.35 * mock_call.SR), dtype=np.float32)

    # Dial gate: reading the brief is free. Calibration + the whisper model
    # load happen after ENTER, so transcription isn't cold on turn 1.
    if not text_mode:
        print()
        try:
            input("  Read the brief. Press ENTER to dial... ")
        except KeyboardInterrupt:
            print("\n\n  Call abandoned before it started.\n")
            sys.exit(130)
        except EOFError:
            print("\n\n  No input (dry pipe). Call never started.\n")
            sys.exit(130)
        recorder.calibrate()
        transcriber._load()

    # Dial: the pickup comes from the LLM (buyer reply 1 of the cap).
    try:
        raw = _next_buyer_line(state, messages, "", warmth, 1, max_turns,
                               difficulty, script_rng, profile, state.model,
                               transport, provider)
    except KeyboardInterrupt:
        # Nothing persisted yet -- do not claim a partial save.
        print("\n\n  Call abandoned before the buyer picked up.\n")
        sys.exit(130)
    hung_up = riq_prompts.is_hangup(raw)
    if hung_up:
        print("\n  *click* (the buyer hung up immediately)\n")
    else:
        spoken = riq_prompts.strip_meta(raw)
        print(f"{brief.persona}: {spoken}")
        if not text_mode:
            state.segments.append(_speak_buyer(spoken, voice, transport, state))
            state.segments.append(pause)
        print()
    try:
        # The pickup was buyer reply 1 of the cap; candidate turn N gets
        # buyer reply N+1, so the loop stops one short of the cap.
        for turn in range(1, max_turns):
            if hung_up:
                break
            q_so_far = sum(grader.count_discovery_questions(t.text)
                           for t in state.turns)
            # objections handled is 0 by definition: objection flags don't
            # exist in a free-form LLM call.
            print(mock_call.hud_line(turn, max_turns, "llm", q_so_far, 0, warmth))

            # ---- candidate turn ------------------------------------------------
            if text_mode:
                said = input("YOU> ").strip()
                recording = mock_call.Recording(np.zeros(0, dtype=np.float32),
                                                None, 0.0, [], froze=not said)
            else:
                # The ready gate: thinking time before arming is free — the
                # recorder measures onset from when the mic opens, not from
                # when the buyer finished. --no-ready-gate restores cold timing.
                if not getattr(args, "no_ready_gate", False):
                    _ready_gate()
                recording = recorder.record_turn()
                print("  transcribing...", end="", flush=True)
                said = transcriber.transcribe(recording.audio)
                print("\r" + " " * 20 + "\r", end="")
                print(f"YOU: {said or '[silence]'}")
                bits = []
                if recording.onset is not None:
                    bits.append(f"first word after {recording.onset:.1f}s")
                if recording.duration:
                    bits.append(f"{recording.duration:.0f}s")
                if recording.gaps:
                    bits.append("gaps " + ", ".join(f"{g:.1f}s"
                                                    for g in recording.gaps))
                if bits:
                    print(f"     ({'; '.join(bits)})")
                # Both sides of the call land in the session mix. Wave-1 order:
                # the offset is recorded BEFORE this turn's audio is appended.
                state.turn_starts.append(
                    sum(s.size for s in state.segments) / mock_call.SR)
                state.segments.append(recording.audio)
                state.segments.append(pause)

            state.turns.append(grader.Turn(
                index=turn, stage_id="llm", expects="", pm_line=spoken,
                text=said, onset_latency=recording.onset,
                duration=recording.duration, internal_gaps=recording.gaps,
                is_objection=False, objection_label="",
                froze=recording.froze and not said))
            warmth = grader.warmth_update(warmth, grader.has_question(said))

            # ---- buyer reply (RAW text; meta lines still inside) ----------------
            raw = _next_buyer_line(state, messages, said, warmth, turn + 1,
                                   max_turns, difficulty, script_rng, profile,
                                   state.model, transport, provider)
            if riq_prompts.is_hangup(raw):
                # Checked on the RAW reply BEFORE anything is spoken, shown,
                # or graded: a compliant lone [[HANGUP]] must never reach the
                # TTS/display path. The buyer hung up — the call is over.
                hung_up = True
                print("\n  *click* (the buyer hung up)\n")
                break
            spoken = riq_prompts.strip_meta(raw)
            print(f"{brief.persona}: {spoken}")
            if not text_mode:
                state.segments.append(_speak_buyer(spoken, voice, transport,
                                                   state))
                state.segments.append(pause)
            print()

        if not hung_up:
            print("\n  *click* (turn cap reached)\n")
    except EOFError:
        # Dry pipe in --text mode: the call is over, not crashed. Save what we
        # have and end the rep gracefully (KeyboardInterrupt et al. re-raise).
        state.partial = True
        _persist(outdir, session_id, state, brief, args, text_mode)
        return
    except BaseException:
        state.partial = True
        _persist(outdir, session_id, state, brief, args, text_mode)
        raise
    _persist(outdir, session_id, state, brief, args, text_mode)
