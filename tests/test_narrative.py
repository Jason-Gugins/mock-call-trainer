"""Career narrative + 2018-2023 gap-answer drill scoring.

Grades the discrete required elements (evidence, concision, no hedging, a gap
that pivots forward) rather than judging the whole narrative.

    .venv/Scripts/python.exe tests/test_narrative.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader as G


class ScoreNarrative(unittest.TestCase):
    def test_why_sales_with_evidence_passes(self):
        self.assertEqual(G.score_narrative_shot(
            "why_sales",
            "I'm moving into sales because I love working off numbers and "
            "proving things with data. My outbound project shows that."), [])

    def test_hedging_is_flagged(self):
        missing = G.score_narrative_shot(
            "why_sales", "I think sales is probably something I'd be good at, I guess.")
        self.assertIn("hedging language", missing)

    def test_rambling_is_flagged(self):
        missing = G.score_narrative_shot(
            "why_company", " ".join(["Because the company is great and their product helps customers. "] * 25))
        self.assertTrue(any("wrong length" in m for m in missing))

    def test_gap_pivots_forward(self):
        self.assertEqual(G.score_narrative_shot(
            "gap",
            "After 2018 I focused on self-study and then launched a self-taught "
            "outbound project to prove I can sell."), [])

    def test_gap_without_pivot_is_flagged(self):
        missing = G.score_narrative_shot("gap", "There was a gap, and I was not working.")
        self.assertIn("missing gap evidence", missing)

    def test_why_company_needs_specificity(self):
        missing = G.score_narrative_shot("why_company", "I just think it would be a good fit.")
        self.assertIn("missing why_company evidence", missing)

    def test_probably_is_a_hedge(self):
        missing = G.score_narrative_shot(
            "why_sales",
            "Sales is probably right for me because I love working off numbers and data.")
        self.assertTrue(any("hedging" in m for m in missing))


class NarrativeHelpers(unittest.TestCase):
    def test_render_and_history_exist(self):
        self.assertTrue(hasattr(G, "render_narrative_markdown"))
        self.assertTrue(hasattr(G, "append_narrative_history"))


if __name__ == "__main__":
    unittest.main()
