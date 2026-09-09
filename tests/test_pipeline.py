"""
End-to-end check of the audio path without a human: synthesise a spoken answer
with Windows TTS, run it through the transcriber, then confirm the grader picks
the construction vocabulary back out of it.

    .venv\\Scripts\\python.exe tests\\test_pipeline.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader                                    # noqa: E402
from mock_call import SR, Transcriber, _resample  # noqa: E402

SPOKEN = (
    "Thirty years, that's no fluke, and I'm not going to tell you paper's the problem. "
    "When a drawing gets revised, how do you know the field isn't still building off the "
    "superseded set? And how are you tracking RFIs and submittals across your jobs today, "
    "or the change orders at closeout?"
)


def synth(text: str, path: Path, voice: str = "Microsoft Zira Desktop") -> None:
    txt = path.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"try {{ $s.SelectVoice('{voice}') }} catch {{}}; "
        f"$s.SetOutputToWaveFile('{path}'); "
        f"$t = Get-Content -Raw -LiteralPath '{txt}'; "
        "$s.Speak($t); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   check=True, capture_output=True, timeout=120)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mockcall_test_"))
    wav = tmp / "spoken.wav"

    print("1. Synthesising a spoken answer with Windows TTS...")
    synth(SPOKEN, wav)
    data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    audio = _resample(data.mean(axis=1), sr, SR)
    print(f"   {len(audio)/SR:.1f}s of audio at {SR} Hz")

    print("2. Transcribing with faster-whisper (downloads model on first run)...")
    text = Transcriber("base.en").transcribe(audio)
    print(f"   heard: {text}")

    print("3. Grading the transcript...")
    terms = grader.find_matches(text, grader.HIGH_VALUE_TERMS)
    qs = grader.count_discovery_questions(text)
    ack = grader.is_acknowledged(text)
    banned = grader.find_matches(text, grader.BANNED_PHRASES)
    print(f"   construction terms detected : {terms}")
    print(f"   targeted questions          : {qs}")
    print(f"   acknowledged first          : {ack}")
    print(f"   banned filler               : {banned or 'none'}")

    ok = len(terms) >= 3 and qs >= 2 and ack and not banned
    print()
    print("PASS - speech pipeline and grader agree." if ok else
          "FAIL - check transcription quality or try --model small.en")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
