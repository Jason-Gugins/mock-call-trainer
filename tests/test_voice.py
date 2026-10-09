"""Voice selection: pure matching only (no PowerShell in tests)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mock_call
import profiles


class BestVoiceTests(unittest.TestCase):
    INSTALLED = ["Microsoft David Desktop", "Microsoft Zira Desktop",
                 "Microsoft Hazel Desktop"]

    def test_exact_match(self):
        self.assertEqual(mock_call.best_voice("Microsoft Zira Desktop", self.INSTALLED),
                         "Microsoft Zira Desktop")

    def test_case_insensitive_substring(self):
        self.assertEqual(mock_call.best_voice("zira", self.INSTALLED),
                         "Microsoft Zira Desktop")

    def test_no_match(self):
        self.assertIsNone(mock_call.best_voice("Cortana", self.INSTALLED))

    def test_empty_request(self):
        self.assertIsNone(mock_call.best_voice("", self.INSTALLED))


class ProfileVoiceTests(unittest.TestCase):
    def test_profiles_declare_voices(self):
        self.assertEqual(profiles.get_profile("boostsecurity").tts_voice,
                         "Microsoft Zira Desktop")
        self.assertEqual(profiles.get_profile("generic_saas").tts_voice,
                         "Microsoft David Desktop")

    def test_default_is_empty_for_new_profiles(self):
        # A Profile built without tts_voice must not break register().
        p = profiles.Profile(
            name="x", display="x", company="x", buyer_name="x", buyer_title="x",
            objective="x", difficulty_rates={}, pickup={}, react_opener={},
            objection_pools={}, pain_reveal=[], pain_drill_cues=[],
            high_value_terms={}, contextual_terms={}, whisper_primer="",
            freeze_prompts=[], sign_off={})
        self.assertEqual(p.tts_voice, "")


if __name__ == "__main__":
    unittest.main()
