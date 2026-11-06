"""Shared seams the wave-2 drill modules reuse.

Two seams are promoted so the new drills import them instead of
re-implementing: mock_call.ready_gate (the "press any key when you're ready"
mic-arm gate, moved verbatim out of llm_call._ready_gate) and
riq_grade.RIQ_CHALLENGE_RE (the RIQ challenge-question pattern, promoted from
a grade_riq function local). llm_call keeps working through the same public
name; the drills arm their mics and score challenge questions through these
exact seams.
"""
from __future__ import annotations

import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm_call
import mock_call
import riq_grade


class ReadyGateSeamTests(unittest.TestCase):
    def test_ready_gate_is_public_on_mock_call(self):
        self.assertTrue(hasattr(mock_call, "ready_gate"))
        self.assertTrue(callable(mock_call.ready_gate))

    def test_llm_call_uses_the_shared_gate(self):
        # The private copy is gone; llm_call resolves the gate through
        # mock_call and re-exports the name so the seam is reachable from
        # either module.
        self.assertFalse(hasattr(llm_call, "_ready_gate"))
        self.assertIs(llm_call.ready_gate, mock_call.ready_gate)

    def test_ready_gate_patches_cleanly(self):
        # The drills (and their tests) patch mock_call.ready_gate; reaching
        # the name through llm_call must never raise AttributeError.
        with mock.patch.object(mock_call, "ready_gate") as fake:
            mock_call.ready_gate()
            self.assertEqual(fake.call_count, 1)
            self.assertTrue(callable(llm_call.ready_gate))

    @unittest.skipUnless(sys.platform == "win32", "msvcrt key path")
    def test_windows_keypress_arms_the_mic(self):
        buf = io.StringIO()
        with mock.patch("msvcrt.getch", return_value=b" ") as getch, \
                redirect_stdout(buf):
            self.assertIsNone(mock_call.ready_gate())
        self.assertEqual(getch.call_count, 1)
        self.assertIn("press any key when you're ready", buf.getvalue())

    @unittest.skipUnless(sys.platform == "win32", "msvcrt key path")
    def test_windows_arrow_key_second_byte_is_swallowed(self):
        with mock.patch("msvcrt.getch",
                        side_effect=[b"\xe0", b"M"]) as getch, \
                redirect_stdout(io.StringIO()):
            self.assertIsNone(mock_call.ready_gate())
        self.assertEqual(getch.call_count, 2)

    @unittest.skipUnless(sys.platform == "win32", "msvcrt key path")
    def test_windows_ctrl_c_raises_keyboard_interrupt(self):
        with mock.patch("msvcrt.getch", return_value=b"\x03"), \
                redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                mock_call.ready_gate()

    def test_non_windows_falls_back_to_enter_prompt(self):
        prompts = []

        def fake_input(prompt=""):
            prompts.append(prompt)
            return ""

        with mock.patch.object(mock_call.sys, "platform", "linux"), \
                mock.patch("builtins.input", fake_input):
            mock_call.ready_gate()
        self.assertEqual(len(prompts), 1)
        self.assertIn("press ENTER when you're ready", prompts[0])


class RiqChallengeReTests(unittest.TestCase):
    REAL_DEBRIEF_CHALLENGE = (
        "how are you getting show-specific emails out without spending half "
        "your week exporting and cleaning lists?")

    def test_pattern_is_public_module_constant(self):
        self.assertTrue(hasattr(riq_grade, "RIQ_CHALLENGE_RE"))

    def test_matches_the_real_debrief_challenge_shape(self):
        self.assertTrue(re.search(riq_grade.RIQ_CHALLENGE_RE,
                                  self.REAL_DEBRIEF_CHALLENGE))

    def test_negative_control_contented_buyer_does_not_match(self):
        self.assertFalse(re.search(riq_grade.RIQ_CHALLENGE_RE,
                                   "we're fine, honestly."))


if __name__ == "__main__":
    unittest.main()
