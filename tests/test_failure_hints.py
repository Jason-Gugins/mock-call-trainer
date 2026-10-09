"""failure_hint(): classify the common startup failures into actionable hints."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mock_call


class FailureHintTests(unittest.TestCase):
    def test_mic(self):
        exc = OSError("No default input device available")
        hint = mock_call.failure_hint(exc)
        self.assertIn("--list-devices", hint)
        self.assertIn("--text", hint)

    def test_mic_portaudio(self):
        exc = type("PortAudioError", (Exception,), {})("device unavailable")
        self.assertIn("--list-devices", mock_call.failure_hint(exc))

    def test_model_download(self):
        exc = RuntimeError("Could not download the model from Hugging Face")
        hint = mock_call.failure_hint(exc)
        self.assertIn("model", hint.lower())
        self.assertIn("tiny.en", hint)

    def test_unknown_still_readable(self):
        hint = mock_call.failure_hint(ValueError("weird"))
        self.assertIn("ValueError", hint)
        self.assertIn("weird", hint)


if __name__ == "__main__":
    unittest.main()
