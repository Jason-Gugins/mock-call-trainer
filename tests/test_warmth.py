"""Buyer temperature gauge: helpers, report rendering, history.csv untouched."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader as G


def _report(warmth):
    crit = G.CriterionResult("c", "PASS", "d", "", key="c1_industry_language")
    return G.Report(criteria=[crit], leaks=[], verdict="YES -- fine.",
                    passed_count=1, coach_first=[], turns=[], difficulty="normal",
                    warmth_path=warmth)


class WarmthBarTests(unittest.TestCase):
    def test_bands_and_bounds(self):
        # Bands: HOT >= 75, WARM >= 50, COOL >= 25, else COLD.
        # Sample points chosen inside bands (20 sits below the COOL line).
        self.assertEqual(G.warmth_label(80), "HOT")
        self.assertEqual(G.warmth_label(50), "WARM")
        self.assertEqual(G.warmth_label(30), "COOL")
        self.assertEqual(G.warmth_label(20), "COLD")
        self.assertEqual(G.warmth_label(0), "COLD")
        # clamps, never crashes
        self.assertEqual(G.warmth_bar(-5), G.warmth_bar(0))
        self.assertEqual(G.warmth_bar(105), G.warmth_bar(100))

    def test_bar_shape(self):
        bar = G.warmth_bar(50)
        self.assertIn("50%", bar)
        self.assertIn("█", bar)
        self.assertIn("░", bar)


class RenderTests(unittest.TestCase):
    def test_markdown_shows_trajectory_when_present(self):
        md = G.render_markdown(_report([50, 62, 44]), "s1", "session.wav")
        self.assertIn("Buyer temperature", md)
        self.assertIn("50 &rarr; 62 &rarr; 44", md)

    def test_markdown_omits_when_empty(self):
        md = G.render_markdown(_report([]), "s1", "session.wav")
        self.assertNotIn("Buyer temperature", md)

    def test_console_shows_trajectory(self):
        out = G.render_console(_report([50, 44]))
        self.assertIn("BUYER TEMPERATURE", out)
        self.assertIn("50 -> 44", out)

    def test_history_fields_unchanged(self):
        # Guard: the whole point is no history.csv schema drift in wave 1.
        self.assertNotIn("warmth", G.HISTORY_FIELDS)


if __name__ == "__main__":
    unittest.main()
