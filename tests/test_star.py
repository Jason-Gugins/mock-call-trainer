"""STAR story drill scoring.

Grades a behavioural story for the three things the progress report says to
rehearse until automatic: a specific number, a full Situation-Task-Action-Result
arc, and (in voice mode) a 45-90s length.

    .venv/Scripts/python.exe tests/test_star.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader as G


FULL_STAR = (
    "At Tim Hortons I was asked to cut drive-thru times. I measured the bottlenecks "
    "at the window and rebuilt the lane workflow. In the end the average order time "
    "dropped from 45 seconds to 25 seconds and our district ranking rose to the top 5."
)


class ScoreStarShot(unittest.TestCase):
    def test_full_star_with_number_passes(self):
        missing = G.score_star_shot(FULL_STAR, duration=70)
        self.assertEqual(missing, [])

    def test_number_required(self):
        missing = G.score_star_shot(
            "I just did my best at work and it went okay.", duration=60)
        self.assertIn("a specific number", missing)

    def test_wrong_length_flags(self):
        missing = G.score_star_shot(FULL_STAR, duration=15)
        self.assertIn("wrong length", missing)

    def test_text_mode_ignores_length(self):
        self.assertEqual(G.score_star_shot(FULL_STAR, duration=None), [])

    def test_missing_result_arc(self):
        missing = G.score_star_shot(
            "At Tim Hortons I was asked to cut times. I measured and rebuilt the flow.",
            duration=60)
        self.assertIn("result", missing)

    def test_missing_situation(self):
        missing = G.score_star_shot(
            "I cut our drive-thru time in half by reworking the lane. Result was a top-5 ranking.",
            duration=60)
        self.assertIn("situation", missing)

    def test_broadened_action_and_result_recognized(self):
        missing = G.score_star_shot(
            "When our biggest account was at risk, I negotiated better terms and sold two "
            "new modules. Profit rose 20% that quarter.", duration=60)
        self.assertNotIn("action", missing)
        self.assertNotIn("result", missing)
        self.assertNotIn("situation", missing)

    def test_rambling_with_lone_so_not_solid(self):
        # bare "so" must not satisfy the result arc.
        missing = G.score_star_shot(
            "When I was at work I had to do my job. I built a thing. "
            "So yeah, there were like 20 people, whatever.", duration=60)
        self.assertIn("result", missing)


class StarSummary(unittest.TestCase):
    def setUp(self):
        import profiles
        self.p = profiles.get_profile("generic_saas")

    def test_star_stories_field_populated(self):
        self.assertGreaterEqual(len(self.p.star_stories), 3)

    def test_history_and_report_helpers_exist(self):
        # smoke: the module-level render/list helpers the drill wires to exist
        self.assertTrue(hasattr(G, "render_star_markdown"))
        self.assertTrue(hasattr(G, "append_star_history"))

    def test_history_has_profile_column(self):
        import csv
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            shots = [G.StarShot(1, "drive-thru times", FULL_STAR, 70.0, [])]
            G.append_star_history(folder / "star_history.csv", "s1", shots, 12.0,
                                  profile="boostsecurity")
            rows = list(csv.DictReader((folder / "star_history.csv").open(encoding="utf-8")))
            self.assertEqual(rows[0]["profile"], "boostsecurity")


if __name__ == "__main__":
    unittest.main()
