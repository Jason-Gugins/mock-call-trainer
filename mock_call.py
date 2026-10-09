"""
Procore SDR mock cold call trainer.

You speak into the mic, a skeptical Senior Project Manager talks back, and at the
end you get graded against Procore's five published role-play criteria plus the
five failure modes from your own job-hunt diagnosis. The whole session is recorded.

    python mock_call.py                      # normal difficulty
    python mock_call.py -d hostile           # tries to end the call in 10 seconds
    python mock_call.py -d apathetic         # "we're fine, paper works"
    python mock_call.py -d timepoor          # interested but standing on a job site
    python mock_call.py --text               # type instead of speak (grader test / silent practice)
    python mock_call.py --list-devices       # find your mic
    python mock_call.py --model small.en     # slower, more accurate transcription

Outputs land in sessions/<timestamp>/: session.wav, report.md, plus a row in
sessions/history.csv so you can watch the reps improve.
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import tempfile
import time
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np

import grader
import persona
import profiles
from grader import Turn
from grader import warmth_update, warmth_bar

ROOT = Path(__file__).resolve().parent
# Overridable so the CLI tests can't append to the real sessions/ and history.csv.
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))
SR = 16_000              # whisper's native rate
BLOCK = 512              # 32 ms at 16 kHz
PM_VOICE = "Microsoft David Desktop"

# Priming the transcriber with the jargon massively improves recognition of
# "RFI", "submittal", "superseded" and friends -- which the grader looks for.
WHISPER_PRIMER = (
    "A cold call with a construction project manager at a general contractor. "
    "Terms used: RFI, submittal, change order, drawing revision, superseded set, "
    "as-built, daily log, punch list, closeout, holdback, look-ahead schedule, "
    "schedule of values, progress billing, T&M ticket, rework, scope gap, "
    "superintendent, foreman, general contractor, Procore."
)


# --------------------------------------------------------------------------
# Audio helpers
# --------------------------------------------------------------------------

def _resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or len(x) == 0:
        return x.astype(np.float32)
    n_out = int(round(len(x) * sr_out / sr_in))
    return np.interp(
        np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x
    ).astype(np.float32)


class Voice:
    """Windows SAPI text-to-speech for the PM, rendered to WAV so it can also be
    mixed into the session recording."""

    def __init__(self, rate: int = 0, enabled: bool = True):
        self.rate = rate
        self.enabled = enabled
        self._tmp = Path(tempfile.mkdtemp(prefix="mockcall_tts_"))
        weakref.finalize(self, self._cleanup, self._tmp)
        self._n = 0

    @staticmethod
    def _cleanup(tmp):
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def say(self, text: str) -> np.ndarray:
        """Speak `text` aloud; return the audio at 16 kHz mono."""
        if not self.enabled:
            return np.zeros(0, dtype=np.float32)
        import soundfile as sf
        import sounddevice as sd

        self._n += 1
        wav = self._tmp / f"line_{self._n:02d}.wav"
        txt = self._tmp / f"line_{self._n:02d}.txt"
        txt.write_text(text, encoding="utf-8")
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"try {{ $s.SelectVoice('{PM_VOICE}') }} catch {{}}; "
            f"$s.Rate = {self.rate}; "
            f"$s.SetOutputToWaveFile('{wav}'); "
            f"$t = Get-Content -Raw -LiteralPath '{txt}'; "
            "$s.Speak($t); $s.Dispose()"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                check=True, capture_output=True, timeout=90,
            )
            data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
        except Exception as exc:                      # noqa: BLE001
            print(f"  (voice unavailable: {exc})")
            return np.zeros(0, dtype=np.float32)

        mono = data.mean(axis=1)
        sd.play(mono, sr)
        sd.wait()
        return _resample(mono, sr, SR)


@dataclass
class Recording:
    audio: np.ndarray
    onset: Optional[float]
    duration: float
    gaps: List[float] = field(default_factory=list)
    froze: bool = False


class Recorder:
    """Records one turn, ending on trailing silence, and measures how long you
    took to start talking (your documented freezing metric)."""

    def __init__(self, device: Optional[int] = None, trailing_silence: float = 3.0,
                 no_speech_timeout: float = 12.0, max_seconds: float = 120.0):
        self.device = device
        self.trailing = trailing_silence
        self.timeout = no_speech_timeout
        self.max_seconds = max_seconds
        self.threshold = 0.008

    def calibrate(self) -> None:
        import sounddevice as sd
        print("  Calibrating background noise, stay quiet for a second...", end="", flush=True)
        buf = sd.rec(int(0.9 * SR), samplerate=SR, channels=1,
                     dtype="float32", device=self.device)
        sd.wait()
        noise = float(np.sqrt(np.mean(buf.astype(np.float32) ** 2)))
        self.threshold = max(noise * 3.5, 0.006)
        print(f" done (noise {noise:.4f}, threshold {self.threshold:.4f})")

    @staticmethod
    def _beep() -> None:
        import sounddevice as sd
        t = np.linspace(0, 0.08, int(SR * 0.08), endpoint=False)
        sd.play((0.18 * np.sin(2 * np.pi * 880 * t)).astype(np.float32), SR)
        sd.wait()

    def record_turn(self) -> Recording:
        import sounddevice as sd

        self._beep()
        print("  [MIC] your turn -- speak now (pause ~3s when you're done)")

        frames: List[np.ndarray] = []
        block_dur = BLOCK / SR
        onset: Optional[float] = None
        silence_run = 0.0
        gaps: List[float] = []
        elapsed = 0.0

        stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                blocksize=BLOCK, device=self.device)
        with stream:
            loud_streak = 0
            while elapsed < self.max_seconds:
                block, _ = stream.read(BLOCK)
                mono = block[:, 0].astype(np.float32)
                frames.append(mono)
                elapsed += block_dur
                rms = float(np.sqrt(np.mean(mono ** 2)))

                if rms > self.threshold:
                    loud_streak += 1
                    if onset is None and loud_streak >= 3:
                        onset = max(0.0, elapsed - 3 * block_dur)
                    if onset is not None and silence_run >= 1.5:
                        gaps.append(silence_run)
                    silence_run = 0.0
                else:
                    loud_streak = 0
                    silence_run += block_dur
                    if onset is None and elapsed >= self.timeout:
                        break
                    if onset is not None and silence_run >= self.trailing:
                        break

        audio = np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
        if onset is None:
            return Recording(audio, None, elapsed, gaps, froze=True)
        speech = max(0.0, elapsed - onset - silence_run)
        return Recording(audio, onset, speech, gaps, froze=False)


class Transcriber:
    def __init__(self, model_name: str = "base.en", beam: int = 5,
                 initial_prompt: Optional[str] = WHISPER_PRIMER):
        self.model_name = model_name
        self.beam = beam
        self.prompt = initial_prompt
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            print(f"  Loading transcription model '{self.model_name}' "
                  f"(first run downloads it)...")
            self._model = WhisperModel(self.model_name, device="cpu",
                                       compute_type="int8")
        return self._model

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size < SR // 4:
            return ""
        model = self._load()
        segments, _ = model.transcribe(
            audio, language="en", beam_size=self.beam,
            vad_filter=True, initial_prompt=self.prompt,
        )
        return " ".join(s.text.strip() for s in segments).strip()


# --------------------------------------------------------------------------
# Did the candidate's turn land? Drives the PM's next line.
# --------------------------------------------------------------------------

HOOK_MARKERS = (
    "talking to", "talking with", "been speaking", "other", "pms", "p m s",
    "contractors", "gcs", "construction act", "payment", "labour", "labor",
    "retire", "rework", "tariff", "market", "shortage", "prompt payment",
    "adjudication", "holdback", "peers",
)


def _landed(stage_id: str, text: str, profile) -> bool:
    ack_q = grader.is_acknowledged(text) and grader.has_question(text)
    low = text.lower()
    if stage_id == "pickup":
        return grader.has_question(text) and 4 <= len(text.split()) <= 80
    if stage_id == "react_opener":
        markers = profile.hook_markers or HOOK_MARKERS
        return any(m in low for m in markers) and not grader.mentions_capability(text)
    if stage_id in ("obj_paper", "obj_status", "obj_burned"):
        return ack_q
    if stage_id == "react_handle_1":
        return grader.has_question(text)
    if stage_id == "pain_reveal":
        return grader.has_question(text)
    if stage_id == "react_handle_2":
        return not grader.find_matches(text, grader.BANNED_PHRASES) and (
            grader.has_question(text) or bool(grader.find_time_offers(text))
        )
    if stage_id == "obj_close":
        return len(grader.find_time_offers(text)) >= 2
    return True


def hud_line(i: int, total: int, stage_id: str, questions: int,
             objections_handled: int, warmth: int) -> str:
    """One-line ledger of the exact numbers the grader will judge."""
    return (f"  [turn {i}/{total} · warmth {warmth}% · "
            f"questions {questions} · objections handled {objections_handled}]")


def failure_hint(exc: Exception) -> str:
    """One actionable line-set for the failures we actually see in the wild."""
    cls = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "portaudio" in cls or "input device" in msg or "unanticipated" in msg \
            or "invalid device" in msg or "no default" in msg:
        return ("  [mic] couldn't open your microphone.\n"
                "       Check it's plugged in and not held exclusively by another app\n"
                "       (Teams/Zoom/Discord do this), then:  python mock_call.py --list-devices\n"
                "       Or practise silently:                     python mock_call.py --text")
    if "download" in msg or "hugging face" in msg or "huggingface" in msg \
            or "connection" in msg or "could not" in msg and "model" in msg:
        return ("  [model] the transcription model failed to load or download.\n"
                "       Connect to the internet once so faster-whisper can fetch it,\n"
                "       or try a smaller model:  python mock_call.py --model tiny.en")
    return f"  [error] {type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------
# The call
# --------------------------------------------------------------------------

@dataclass
class CallState:
    segments: List[np.ndarray] = field(default_factory=list)
    turns: List[Turn] = field(default_factory=list)
    turn_starts: List[float] = field(default_factory=list)
    warmth_path: List[int] = field(default_factory=lambda: [grader.WARMTH_START])
    pain_revealed: bool = False
    meeting_booked: bool = False
    partial: bool = False


def _persist(outdir: Path, session_id: str, state: CallState, args,
             profile, text_mode: bool) -> None:
    report = grader.grade(state.turns, args.difficulty, state.pain_revealed,
                          state.meeting_booked, profile=profile,
                          warmth_path=state.warmth_path,
                          turn_starts=state.turn_starts)
    if state.partial:
        report.verdict = (f"PARTIAL -- call aborted after {len(state.turns)} "
                          f"turn(s). " + report.verdict)
    print(grader.render_console(report))

    if not text_mode:
        parts = [s for s in state.segments if s.size]
        if parts:                      # fixes np.concatenate([]) ValueError
            import soundfile as sf
            full = np.concatenate(parts)
            peak = float(np.max(np.abs(full))) or 1.0
            sf.write(str(outdir / "session.wav"),
                     (full / peak * 0.95).astype(np.float32), SR)

    (outdir / "report.md").write_text(
        grader.render_markdown(report, session_id, "session.wav"), encoding="utf-8")
    grader.append_history(SESSIONS / "history.csv", session_id, report)

    print(f"\n  Report:  {outdir / 'report.md'}")
    if not text_mode:
        print(f"  Audio:   {outdir / 'session.wav'}")
    print(f"  History: {SESSIONS / 'history.csv'}\n")


def run_call(args, script=None) -> None:
    rng = random.Random(args.seed)
    profile = profiles.get_profile(args.profile)
    script = script or persona.build_script(args.difficulty, rng, profile)

    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    outdir = SESSIONS / profile.name / session_id
    outdir.mkdir(parents=True, exist_ok=True)

    text_mode = args.text
    voice = Voice(rate=profile.difficulty_rates[args.difficulty], enabled=not text_mode)
    recorder = None
    transcriber = None
    if not text_mode:
        recorder = Recorder(device=args.device, trailing_silence=args.silence)
        transcriber = Transcriber(args.model, beam=1 if args.fast else 5,
                                  initial_prompt=profile.whisper_primer)

    print()
    print("=" * 72)
    print(f"  MOCK COLD CALL  --  {profile.display}  --  {args.difficulty.upper()}")
    print("=" * 72)
    print(f"  You are Jason, BDR/SDR at {profile.company}. You're cold calling {profile.buyer_name},")
    print(f"  {profile.buyer_title}.")
    print(f"  Objective: {profile.objective}")
    print()
    print("  Rules you're being graded on: industry language, targeted questions,")
    print("  uncover the pain, book the follow-up with TWO specific times, handle")
    print("  objections (acknowledge first, end on a question). No feature talk")
    print("  until you've asked a question and heard the answer.")
    print("=" * 72)
    if not text_mode:
        print("  Wear headphones so the mic doesn't pick up his voice.")
        try:
            recorder.calibrate()
            transcriber._load()
        except Exception as exc:                      # noqa: BLE001
            print(failure_hint(exc))
            sys.exit(2)
    print()
    input("  Press ENTER to dial... ")
    print()

    state = CallState()
    landed = True
    pause = np.zeros(int(0.35 * SR), dtype=np.float32)

    try:
        for i, stage in enumerate(script, start=1):
            if stage.id == "pain_reveal":
                state.pain_revealed = landed
            line = stage.line(state.meeting_booked if stage.id == "resolution" else landed)

            print(f"{profile.buyer_name} (PM): {line}")
            state.segments.append(voice.say(line))
            state.segments.append(pause)

            # ---- candidate turn ------------------------------------------------
            q_so_far = sum(grader.count_discovery_questions(t.text) for t in state.turns)
            obj_handled = sum(1 for t in state.turns if t.is_objection
                              and grader.is_acknowledged(t.text) and grader.has_question(t.text))
            print(hud_line(i, len(script), stage.id, q_so_far, obj_handled,
                           state.warmth_path[-1]))
            if text_mode:
                said = input("YOU> ").strip()
                rec = Recording(np.zeros(0, dtype=np.float32), None, 0.0, [], froze=not said)
            else:
                try:
                    rec = recorder.record_turn()
                except Exception as exc:              # noqa: BLE001
                    print(failure_hint(exc))
                    state.partial = True
                    _persist(outdir, session_id, state, args, profile, text_mode)
                    sys.exit(2)
                if rec.froze:
                    prompt = rng.choice(profile.freeze_prompts)
                    print(f"{profile.buyer_name} (PM): {prompt}")
                    state.segments.append(voice.say(prompt))
                    state.segments.append(pause)
                    try:
                        rec = recorder.record_turn()
                    except Exception as exc:          # noqa: BLE001
                        print(failure_hint(exc))
                        state.partial = True
                        _persist(outdir, session_id, state, args, profile, text_mode)
                        sys.exit(2)
                state.turn_starts.append(sum(s.size for s in state.segments) / SR)
                state.segments.append(rec.audio)
                state.segments.append(pause)
                print("  transcribing...", end="", flush=True)
                said = transcriber.transcribe(rec.audio)
                print("\r" + " " * 20 + "\r", end="")
                print(f"YOU: {said or '[silence]'}")
                bits = []
                if rec.onset is not None:
                    bits.append(f"first word after {rec.onset:.1f}s")
                if rec.duration:
                    bits.append(f"{rec.duration:.0f}s")
                if rec.gaps:
                    bits.append("gaps " + ", ".join(f"{g:.1f}s" for g in rec.gaps))
                if bits:
                    print(f"     ({'; '.join(bits)})")

            state.turns.append(Turn(
                index=i, stage_id=stage.id, expects=stage.expects, pm_line=line,
                text=said, onset_latency=rec.onset, duration=rec.duration,
                internal_gaps=rec.gaps, is_objection=stage.is_objection,
                objection_label=stage.objection_label, froze=rec.froze and not said,
            ))

            landed = _landed(stage.id, said, profile)
            warmth = warmth_update(state.warmth_path[-1], landed)
            state.warmth_path.append(warmth)
            if i > 1:
                print(f"  warmth {warmth_bar(warmth)}")
            if stage.id == "obj_close":
                state.meeting_booked = len(grader.find_time_offers(said)) >= 2
            print()

        sign_off = profile.sign_off[state.meeting_booked]
        print(f"{profile.buyer_name} (PM): {sign_off}")
        state.segments.append(voice.say(sign_off))
        print("\n  *click*\n")
    except EOFError:
        # Dry pipe in --text mode: the call is over, not crashed. Save what we
        # have and end the rep gracefully (KeyboardInterrupt et al. re-raise).
        state.partial = True
        _persist(outdir, session_id, state, args, profile, text_mode)
        return
    except BaseException:
        state.partial = True
        _persist(outdir, session_id, state, args, profile, text_mode)
        raise
    _persist(outdir, session_id, state, args, profile, text_mode)


def list_devices() -> None:
    import sounddevice as sd
    print("Input devices:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"  [{i}] {d['name']}  (channels: {d['max_input_channels']})")
    print(f"\nCurrent default: {sd.query_devices(kind='input')['name']}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Mock cold call trainer (profile-driven: generic_saas default, procore, ...)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-d", "--difficulty", default="normal",
                   choices=persona.DIFFICULTIES,
                   help="normal | hostile | apathetic | timepoor")
    p.add_argument("--text", action="store_true",
                   help="type your answers instead of speaking (no audio)")
    p.add_argument("--model", default="base.en",
                   help="whisper model: tiny.en, base.en, small.en (default base.en)")
    p.add_argument("--fast", action="store_true",
                   help="faster, slightly less accurate transcription")
    p.add_argument("--device", type=int, default=None, help="input device index")
    p.add_argument("--silence", type=float, default=3.0,
                   help="seconds of silence that ends your turn (default 3.0)")
    p.add_argument("--seed", type=int, default=None,
                   help="fix the objection phrasing for a repeatable run")
    p.add_argument("--list-devices", action="store_true", help="list microphones and exit")
    p.add_argument("--drill", action="store_true",
                   help="pain-reveal only: 10 shots / 3 min, grade cost question + speed")
    p.add_argument("--reps", type=int, default=10, help="drill shots (default 10)")
    p.add_argument("--minutes", type=float, default=3.0, help="drill time budget in minutes")
    p.add_argument("--paraphrase", action="store_true",
                   help="say the same idea a different way every time; reused wording is rejected")
    p.add_argument("--objection", action="store_true",
                   help="objection first-15s reflex drill: label, negative-reverse, feel/felt/found")
    p.add_argument("--star", action="store_true",
                   help="STAR story drill: number + full situation/task/action/result arc")
    p.add_argument("--narrative", action="store_true",
                   help="career narrative drill: why sales / why this company / the gap answer")
    p.add_argument("--beat", default="opener",
                   help="paraphrase target: opener, hook, obj_status, discovery, cost, "
                        "obj_burned, close, all, or a comma-separated list (default opener; "
                        "run --list-beats to see the active profile's beats)")
    p.add_argument("--max-run", type=int, default=5,
                   help="paraphrase: identical content words in a row that count as reciting")
    p.add_argument("--jaccard", type=float, default=0.70,
                   help="paraphrase: content-word overlap that counts as reciting")
    p.add_argument("--reseed", action="store_true",
                   help="paraphrase: re-harvest the ban list from past session reports")
    p.add_argument("--reset-bank", action="store_true",
                   help="paraphrase: wipe the ban list and start over")
    p.add_argument("--list-beats", action="store_true",
                   help="paraphrase: show the beats and exit")
    p.add_argument("--profile", default=profiles.DEFAULT_PROFILE,
                   help="company profile to use (see --list-profiles)")
    p.add_argument("--list-profiles", action="store_true",
                   help="list available profiles and exit")
    args = p.parse_args()

    if args.list_profiles:
        print("Available profiles:")
        for name in profiles.list_profiles():
            pr = profiles.get_profile(name)
            print(f"  {name:14} {pr.buyer_name!s:14} {pr.display}")
        return
    if args.list_devices:
        list_devices()
        return
    if args.list_beats:
        import paraphrase
        paraphrase.list_beats(args.profile)
        return
    if args.paraphrase:
        import paraphrase
        paraphrase.run_live(args)
        return
    if args.drill:
        import drill
        drill.run_live(args)
        return
    if args.objection:
        import objection
        objection.run_live(args)
        return
    if args.star:
        import star
        star.run_live(args)
        return
    if args.narrative:
        import narrative
        narrative.run_live(args)
        return
    try:
        run_call(args)
    except KeyboardInterrupt:
        print("\n\n  Call abandoned -- partial session saved. Run it again: reps are the point.\n")
        sys.exit(130)


if __name__ == "__main__":
    main()
