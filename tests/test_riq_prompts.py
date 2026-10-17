"""Master prompt builder: RIQ rules, brief injection, difficulty, output format."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import riq_briefs as B
import riq_prompts as P


class SystemPromptTests(unittest.TestCase):
    def setUp(self):
        self.brief = B.get_brief("A1")
        self.sys = P.build_system_prompt(self.brief, difficulty="normal")

    def test_identity_and_brief_injection(self):
        self.assertIn(self.brief.persona, self.sys)
        self.assertIn(self.brief.title, self.sys)
        self.assertIn(self.brief.external_trigger, self.sys)     # R in prompt
        self.assertIn(self.brief.internal_signal, self.sys)      # I in prompt
        self.assertIn(self.brief.status_quo, self.sys)           # private answer
        for pain in self.brief.pains[:2]:
            self.assertIn(pain, self.sys)

    def test_riq_and_taxonomy_rules_present(self):
        for needle in ("Research", "Insight", "Questioning", "challenge question",
                       "external trigger", "internal signal",
                       "positive triggers sell growth, negative sell efficiency",
                       "neutral triggers build rapport",
                       "ONE question", "NO stage directions",
                       "reveal you are an AI", "[[HANGUP]]"):
            self.assertIn(needle, self.sys)

    def test_difficulty_variants_differ(self):
        normal = P.build_system_prompt(self.brief, "normal")
        hostile = P.build_system_prompt(self.brief, "hostile")
        self.assertIn("skeptical but fair", normal)
        self.assertNotIn("end the call in ten seconds", normal)
        self.assertIn("end the call in ten seconds", hostile)

    def test_output_format_rules(self):
        for needle in ("1-3 short spoken sentences", "[[HANGUP]]",
                       "NO stage directions"):
            self.assertIn(needle, self.sys)

    def test_invalid_difficulty_raises(self):
        with self.assertRaises(ValueError):
            P.build_system_prompt(self.brief, difficulty="furious")


class TurnMessageTests(unittest.TestCase):
    def test_turn_message_carries_candidate_words_and_state(self):
        msg = P.build_turn_message("How are you handling list cleanup today?",
                                   warmth=62, turn=3, max_turns=16)
        self.assertIn("How are you handling list cleanup today?", msg)
        self.assertIn("62", msg)
        self.assertIn("turn 3 of 16", msg)

    def test_warmth_mood_instruction(self):
        hot = P.build_turn_message("go on", warmth=90, turn=2, max_turns=16)
        cool = P.build_turn_message("go on", warmth=30, turn=2, max_turns=16)
        cold = P.build_turn_message("go on", warmth=10, turn=2, max_turns=16)
        self.assertIn("warming", hot)
        self.assertIn("losing patience", cool)
        self.assertIn("one foot out the door", cold)

    def test_meta_helpers(self):
        self.assertEqual(P.strip_meta("We're set for Thursday.\n[[HANGUP]]"),
                         "We're set for Thursday.")
        self.assertEqual(P.strip_meta("[[HANGUP]]"), "")
        self.assertTrue(P.is_hangup("[[HANGUP]]"))
        self.assertTrue(P.is_hangup("Thursday works. Send the invite.\n[[HANGUP]]"))
        self.assertFalse(P.is_hangup("see you Thursday"))


if __name__ == "__main__":
    unittest.main()
