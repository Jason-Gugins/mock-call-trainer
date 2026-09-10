"""Objection first-15-seconds reflex drill scoring.

Trains the reflexes the progress report calls CRITICAL: the first move after a
buyer says "not interested" — Voss labeling, Sandler negative reverse,
feel/felt/found — delivered fast, not a defensive pitch.

    .venv/Scripts/python.exe tests/test_objection.py
"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader as G


class ScoreObjectionShot(unittest.TestCase):
    def test_voss_label_fast(self):
        hit, verdict = G.score_objection_shot(
            "It sounds like this burned you before. What would need to be true for you to look?",
            onset=1.2, froze=False)
        self.assertTrue(hit)
        self.assertEqual(verdict, "FAST")

    def test_negative_reverse_ok(self):
        hit, verdict = G.score_objection_shot(
            "So you're telling me it works fine, and what would have to be true for you to change?",
            onset=2.5, froze=False)
        self.assertTrue(hit)
        self.assertEqual(verdict, "OK")

    def test_cut_in_is_flagged(self):
        hit, verdict = G.score_objection_shot(
            "It sounds like this burned you before.", onset=0.2, froze=False)
        self.assertTrue(hit)
        self.assertEqual(verdict, "CUT-IN")

    def test_feel_felt_found(self):
        hit, verdict = G.score_objection_shot(
            "I felt exactly that with a past team, and found the fix was the rollout. What happened with yours?",
            onset=0.9, froze=False)
        self.assertTrue(hit)
        self.assertEqual(verdict, "FAST")

    def test_curiosity_question_counts(self):
        hit, _ = G.score_objection_shot(
            "I hear you. What actually happened? Was it the tool or the rollout?", onset=0.7, froze=False)
        self.assertTrue(hit)

    def test_defensive_pitch_is_miss(self):
        hit, verdict = G.score_objection_shot(
            "But actually our platform is different, you can track everything in one place.",
            onset=0.5, froze=False)
        self.assertFalse(hit)
        self.assertEqual(verdict, "MISS")

    def test_ack_then_pitch_is_miss(self):
        # a token label pasted in front of a pitch is still a pitch - FAST here
        # would reward the exact talking-past-objections failure mode.
        hit, verdict = G.score_objection_shot(
            "Fair enough, but our platform is different, you can track everything in one place.",
            onset=0.8, froze=False)
        self.assertFalse(hit)
        self.assertEqual(verdict, "MISS")

    def test_felt_alone_is_not_a_reflex(self):
        hit, verdict = G.score_objection_shot(
            "honestly we felt our old vendor was fine", onset=0.4, froze=False)
        self.assertFalse(hit)
        self.assertEqual(verdict, "MISS")

    def test_freeze_is_miss(self):
        hit, verdict = G.score_objection_shot("", onset=None, froze=True)
        self.assertFalse(hit)
        self.assertEqual(verdict, "MISS")

    def test_text_mode_no_clock(self):
        hit, verdict = G.score_objection_shot(
            "Fair enough, what would it take for you to look?", onset=None, froze=False)
        self.assertTrue(hit)
        self.assertEqual(verdict, "HIT")

    def test_curiosity_openers_hit(self):
        for line in ("Can I ask what's behind that?",
                     "What would need to happen for you to reconsider?",
                     "That's fair, I don't blame you."):
            hit, _ = G.score_objection_shot(line, onset=1.0, froze=False)
            self.assertTrue(hit, msg=line)


class ObjectionSummary(unittest.TestCase):
    def test_summary_counts(self):
        shots = [
            G.ObjectionShot(1, "cue", "It sounds like x", 1.0, False, True, "FAST"),
            G.ObjectionShot(2, "cue", "but we offer y", 0.5, False, False, "MISS"),
            G.ObjectionShot(3, "cue", "I hear you, what would it take", 3.0, False, True, "SLOW"),
        ]
        s = G.summarize_objection(shots, 30.0, 10)
        self.assertEqual(s.hits, 2)
        self.assertEqual(s.n, 3)
        self.assertEqual(s.fast, 1)
        self.assertEqual(s.miss, 1)

    def test_csv_writes_only_to_objection_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            shots = [G.ObjectionShot(1, "cue", "It sounds like x", 1.0, False, True, "FAST")]
            G.append_objection_history(folder / "objection_history.csv", "s1", shots, 5.0)
            rows = list(csv.DictReader((folder / "objection_history.csv").open(encoding="utf-8")))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["verdict"], "FAST")
            self.assertFalse((folder / "history.csv").exists())


if __name__ == "__main__":
    unittest.main()
