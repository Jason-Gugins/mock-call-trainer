"""LLM call loop: full flow with fake transport + text mode; fallback path."""
from __future__ import annotations

import csv
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm_call


def _args(**kw):
    base = dict(difficulty="normal", brief="A1", text=True, seed=7,
                max_turns=16, llm_model="fake/model", profile="generic_saas",
                model="base.en", fast=False, device=None, silence=3.0)
    base.update(kw)
    return types.SimpleNamespace(**base)


class _Scripted:
    """Fake transport: every chat call returns the next scripted buyer line."""
    def __init__(self, lines):
        self.lines = list(lines)
        self.chat_calls = 0

    def __call__(self, path, payload):
        if path == "/chat/completions":
            self.chat_calls += 1
            if not self.lines:
                return {"choices": [{"message": {"content": "[[HANGUP]]"}}]}
            return {"choices": [{"message": {"content": self.lines.pop(0)}}]}
        raise AssertionError(f"unexpected path {path}")


class LlmCallTests(unittest.TestCase):
    def _run(self, tmp, transport, lines, **kw):
        old = llm_call.SESSIONS
        llm_call.SESSIONS = Path(tmp)
        it = iter(lines)

        def fake_input(prompt=""):
            try:
                return next(it)
            except StopIteration:
                raise EOFError          # dry pipe: graceful partial, like run_call

        args = _args(**kw)
        try:
            with mock.patch("builtins.input", fake_input):
                llm_call.run_llm_call(args, transport=transport)
        finally:
            llm_call.SESSIONS = old

    def test_full_call_persists_report_and_history(self):
        lines = [
            "Hi Susie, this is Jason with AudienceView. I know I'm calling you "
            "out of the blue: do you have thirty seconds so I can tell you why I "
            "called, and then you can decide if we keep talking?",
            "So the reason I'm calling: season subscriptions are turning into "
            "memberships and flex passes, and I saw you've got shows most "
            "weekends with a team of two. How are you getting show emails out "
            "without spending half your week cleaning lists — what does that "
            "cost you?",
            "By hand, every campaign. Who eats that when it piles up?",
            "That's exactly why I'm calling. Open to fifteen minutes Thursday "
            "at 10 or Friday at 2?",
        ]
        t = _Scripted([
            "Sure, but make it quick, on-sale week.",
            "Honestly? Ticketing in one place, email in another. I export and "
            "clean lists by hand, every single campaign.",
            "The better part of a day, some weeks.",
            "Alright, Thursday works. Send the invite.\n[[HANGUP]]",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, t, lines)
            md = list(Path(tmp).glob("**/report.md"))[0].read_text(encoding="utf-8")
            self.assertIn("Susie", md)                 # brief card in report
            self.assertIn("RIQ", md)                   # renderer contract token
            self.assertNotIn("FALLBACK", md)
            rows = list(csv.DictReader(
                (Path(tmp) / "llm_history.csv").open(encoding="utf-8")))
            self.assertEqual(rows[0]["brief"], "A1")
            self.assertEqual(rows[0]["fallback"], "N")

    def test_hangup_line_is_not_spoken_or_graded(self):
        # The buyer's LAST reply carries [[HANGUP]]: it ends the call before
        # reaching any speak/display path, after all four candidate turns.
        t = _Scripted(["Sure, make it quick, on-sale week.",
                       "We manage, honestly.",
                       "Send me something in writing first.",
                       "Maybe. What would it show me?",
                       "Alright, Thursday works. Send the invite.\n[[HANGUP]]"])
        lines = ["Hi, got a minute?", "Are you handling this by hand?",
                 "What does that cost you?", "Thursday at 10 or Friday at 2?"]
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, t, lines)
            rows = list(csv.DictReader(
                (Path(tmp) / "llm_history.csv").open(encoding="utf-8")))
            self.assertEqual(int(rows[0]["turns"]), len(lines))
            # pickup + 3 spoken replies; the hangup reply never gets a 5th call
            self.assertEqual(t.chat_calls, 5)

    def test_instant_hangup_at_pickup_writes_empty_report(self):
        t = _Scripted(["[[HANGUP]]"])
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, t, ["Hello?"])     # EOF after 1 line; loop never runs
            rows = list(csv.DictReader(
                (Path(tmp) / "llm_history.csv").open(encoding="utf-8")))
            self.assertEqual(int(rows[0]["turns"]), 0)

    def test_api_death_falls_back_to_scripted_buyer(self):
        class _Dies:
            calls = 0

            def __call__(self, path, payload):
                if _Dies.calls >= 1:               # pickup OK, then the API dies
                    raise llm_call.OpenRouterError("boom")
                _Dies.calls += 1
                return {"choices": [{"message": {"content": "Go ahead."}}]}

        lines = (["Hi Susie.", "Do you handle this by hand today?",
                  "What does that cost you?", "Thursday at 10 or Friday at 2?"]
                 * 4)                              # longer than the scripted stages
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, _Dies(), lines)
            md = list(Path(tmp).glob("**/report.md"))[0].read_text(encoding="utf-8")
            self.assertIn("FALLBACK", md)
            rows = list(csv.DictReader(
                (Path(tmp) / "llm_history.csv").open(encoding="utf-8")))
            self.assertEqual(rows[0]["fallback"], "Y")

    def test_dry_pipe_saves_partial_gracefully(self):
        # Enough buyer lines that the BUYER never hangs up: the piped input
        # running dry (EOF) is what ends this call -> graceful PARTIAL save.
        t = _Scripted(["Sure, go ahead.", "We manage, honestly.",
                       "Send me something in writing first.",
                       "Alright.", "Okay."])
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, t, ["Hi Susie."])       # input runs dry after 1 turn
            md = list(Path(tmp).glob("**/report.md"))[0].read_text(encoding="utf-8")
            self.assertIn("PARTIAL", md)

    def test_missing_brief_errors_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(KeyError):
                self._run(tmp, _Scripted([]), ["x"], brief="Z9")


if __name__ == "__main__":
    unittest.main()
