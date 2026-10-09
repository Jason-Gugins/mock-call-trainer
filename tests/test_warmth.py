"""Buyer temperature gauge: helpers, report rendering, history.csv untouched."""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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


WARM_CALL = [
    # 9 candidate turns in stage order; landing every beat keeps warmth >= 50
    "Alex, you don't know me and this is a cold call out of the blue. "
    "Can I take thirty seconds to tell you why I called? If it's not for you, "
    "just say no and hang up and I'm gone.",
    "I work with a lot of VPs of Operations, and the same thing keeps coming up: "
    "marketing hands sales a pile of leads, and half of them die in the follow-up "
    "gap before anyone picks up the phone. Is that showing up in your pipeline?",
    "That's fair, and I won't pretend your process is broken when you're hitting "
    "your numbers. When a rep leaves, though, how much of the CRM history walks "
    "out the door with them?",
    "Walk me through your follow-up process. When a deal stalls, how does the "
    "rep know what got promised to that customer?",
    "Ouch. When that follow-up gap eats a quarter, what does that do to your "
    "forecast — do you find out before the number slips, or after?",
    "I hear you, and I don't blame you — that happens more than vendors admit. "
    "Was it the tool itself, or the rollout that never gave the team a reason "
    "to open it?",
    "That's fair. The ones that stick start with one team, one pipeline, and a "
    "reason to open it every morning. Would it be worth looking at your "
    "follow-up numbers together, or should I show your team the flow?",
    "Completely fair. Instead of an email you'll never open — I've got Tuesday "
    "at 10, or Thursday at 2. Which one should I put on the calendar?",
    "Perfect, Tuesday at 10 it is. I'll send the invite tonight. So I can prep — "
    "what do you want your AE to come ready to cover?",
]


class LiveLoopTests(unittest.TestCase):
    def _run_text_call(self, lines, tmp, eof=False):
        import mock_call as m
        old = m.SESSIONS
        m.SESSIONS = Path(tmp)
        args = types.SimpleNamespace(
            difficulty="normal", profile="generic_saas", text=True, seed=None,
            model="base.en", fast=False, device=None, silence=3.0,
        )
        it = iter(lines)

        def fake_input(prompt=""):
            try:
                return next(it)
            except StopIteration:
                if eof:
                    raise EOFError   # what real input() does when a pipe runs dry
                return ""            # a frozen (silent) turn

        try:
            with mock.patch("builtins.input", fake_input):
                m.run_call(args)
        finally:
            m.SESSIONS = old

    def test_warmth_path_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._run_text_call(WARM_CALL, tmp)
            reports = list(Path(tmp).glob("**/report.md"))
            self.assertEqual(len(reports), 1)
            md = reports[0].read_text(encoding="utf-8")
            self.assertIn("Buyer temperature", md)

    def test_partial_pipe_saves_on_eof(self):
        # Piped input runs dry after 3 turns: the EOFError becomes a graceful
        # PARTIAL save (crash-safe net landed in Task 4).
        with tempfile.TemporaryDirectory() as tmp:
            self._run_text_call(WARM_CALL[:3], tmp, eof=True)
            reports = list(Path(tmp).glob("**/report.md"))
            self.assertEqual(len(reports), 1)
            self.assertIn("PARTIAL", reports[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
