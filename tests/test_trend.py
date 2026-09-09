"""Cross-session progression renderer.

    .venv/Scripts/python.exe tests/test_trend.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import trend  # noqa: E402


ROWS = [
    {"session": "s1", "criteria_passed": "4", "opener_latency": "1.7s",
     "ack_rate": "66%", "filler_rate": "2 in 349 words (0.6/100)",
     "longest_turn": "84 words", "banned_words": "0 hit(s)",
     "freezes": "none", "talk_time": "106s"},
    {"session": "s2", "criteria_passed": "5", "opener_latency": "0.2s",
     "ack_rate": "100%", "filler_rate": "7 in 480 words (1.5/100)",
     "longest_turn": "92 words", "banned_words": "1 hit(s)",
     "freezes": "turns 3", "talk_time": "144s"},
]


class Parse(unittest.TestCase):
    def test_num(self):
        self.assertEqual(trend._num("0.2s"), 0.2)
        self.assertEqual(trend._num("100%"), 100)
        self.assertEqual(trend._num("92 words"), 92)
        self.assertEqual(trend._num("4"), 4)
        self.assertIsNone(trend._num("none"))
        self.assertIsNone(trend._num("n/a"))

    def test_filler_rate_is_per_100_not_count(self):
        self.assertEqual(trend._filler_rate("2 in 349 words (0.6/100)"), 0.6)
        self.assertEqual(trend._filler_rate("7 in 480 words (1.5/100)"), 1.5)
        # no (rate/100) group: falls back to the generic parser, which treats
        # strings starting with 'no' as missing
        self.assertIsNone(trend._filler_rate("no filler"))


class Tabulate(unittest.TestCase):
    def test_one_row_per_session(self):
        out = trend.tabulate(ROWS)
        self.assertEqual(out.count("s1"), 1)
        self.assertEqual(out.count("s2"), 1)

    def test_header_present(self):
        self.assertIn("session", trend.tabulate(ROWS))
        self.assertIn("crit", trend.tabulate(ROWS))

    def test_filler_column_shows_rate_not_count(self):
        # regression: this previously rendered the raw count (2 / 7), not the
        # per-100-word rate (0.6 / 1.5) promised by the column legend.
        out = trend.tabulate(ROWS)
        self.assertIn("0.6", out)
        self.assertIn("1.5", out)
        self.assertNotIn("2 in", out)
        self.assertNotIn("7 in", out)


if __name__ == "__main__":
    unittest.main()
