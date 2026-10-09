"""Listen-back HTML: embedded audio + clickable per-turn timeline."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader as G
import listenback


def _rep():
    crit = G.CriterionResult("c", "PASS", "d", "", key="c1_industry_language")
    t1 = G.Turn(index=1, stage_id="pickup", expects="", pm_line="Alex Moore.",
                text="Hello there <boss> & friend", onset_latency=0.8, duration=5.0)
    t2 = G.Turn(index=2, stage_id="react_opener", expects="", pm_line="Go ahead.",
                text="Second turn", onset_latency=0.8, duration=7.0)
    return G.Report(criteria=[crit], leaks=[], verdict="YES -- fine.",
                    passed_count=1, coach_first=[], turns=[t1, t2],
                    difficulty="normal", warmth_path=[50, 62],
                    turn_starts=[0.0, 12.5])


class ListenbackTests(unittest.TestCase):
    def test_renders_audio_and_seek_buttons(self):
        html = listenback.render("2026-10-07_120000", _rep(), b"FAKEWAV")
        self.assertIn("<audio", html)
        self.assertIn("data:audio/wav;base64,", html)
        self.assertIn("RkFLRVdBVg==", html)            # b"FAKEWAV" base64
        self.assertIn('data-start="12.5"', html)
        self.assertIn("data-start=\"0.0\"", html)

    def test_turn_text_is_escaped(self):
        html = listenback.render("s", _rep(), b"w")
        self.assertIn("&lt;boss&gt; &amp; friend", html)
        self.assertNotIn("<boss>", html)

    def test_starts_shorter_than_turns_is_safe(self):
        rep = _rep()
        rep.turn_starts = [0.0]
        html = listenback.render("s", rep, b"w")       # zip() truncates, no crash
        self.assertIn('data-start="0.0"', html)


if __name__ == "__main__":
    unittest.main()
