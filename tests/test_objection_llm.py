"""LLM objection escalation drill (--objection --llm): offline seam tests.

The session core takes injected seams (capture, react, now, speak_cue), so the
whole loop is testable without audio libs or network: pool cycling, the
silent-skip net for a dead reaction API, the deterministic score components,
and the history CSV (written into a temp SESSIONS). The voice path is not
tested here — it is exercised only in live runs.

    .venv/Scripts/python.exe -m unittest tests.test_objection_llm -v
"""
from __future__ import annotations

import contextlib
import csv
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import objection_llm
from openrouter_client import OpenRouterError

GOOD = "Fair enough, what would it take for you to look?"
PITCH = "Actually, our platform puts everything in one place, you can track it all."


def _brief():
    """Small brief: 2 objections + objection.BRUSH_OFFS (4) = a 6-line pool.

    The objections deliberately do NOT overlap BRUSH_OFFS so uniqueness
    assertions are exact."""
    return types.SimpleNamespace(
        id="A1", persona="Susie", title="marketing director",
        company_desc="a mid-size theatre",
        objections=["We already have a process for this.",
                    "Your competitor is cheaper."])


def _capture(responses):
    it = iter(responses)
    calls = []

    def capture():
        calls.append(1)
        return next(it), None, False     # text mode: onset None, never froze
    capture.calls = calls
    return capture


class PoolTests(unittest.TestCase):
    def test_eight_rounds_no_repeat_until_pool_exhausted(self):
        brief = _brief()
        reps = 8                                   # pool is 2 + 4 = 6 lines
        capture = _capture([GOOD] * reps)
        shots, line = objection_llm.run_objection_llm_session(
            reps=reps, seed=11, brief=brief, difficulty="normal", capture=capture)
        self.assertEqual(len(shots), reps)
        self.assertEqual([s.round for s in shots], list(range(1, reps + 1)))
        self.assertEqual(len(capture.calls), reps)
        pool = set(brief.objections) | set(objection_llm.BRUSH_OFFS)
        for s in shots:
            self.assertIn(s.objection, pool)
        first_six = [s.objection for s in shots[:6]]
        self.assertEqual(len(set(first_six)), 6)   # no repeats within the pool
        # reps exceed the pool -> the seeded order cycles, it does not reshuffle
        self.assertEqual(shots[6].objection, shots[0].objection)
        self.assertEqual(shots[7].objection, shots[1].objection)
        self.assertIn("8/8 reflexive", line)

    def test_seed_makes_the_order_deterministic(self):
        kw = dict(reps=6, seed=5, brief=_brief(), difficulty="normal")
        a, _ = objection_llm.run_objection_llm_session(capture=_capture([GOOD] * 6), **kw)
        b, _ = objection_llm.run_objection_llm_session(capture=_capture([GOOD] * 6), **kw)
        self.assertEqual([s.objection for s in a], [s.objection for s in b])


class DeadApiTests(unittest.TestCase):
    def test_dead_react_prints_note_once_and_degrades_to_local(self):
        calls = []

        def react(objection, rnd):
            calls.append((objection, rnd))
            raise OpenRouterError("boom")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, _line = objection_llm.run_objection_llm_session(
                reps=3, seed=3, brief=_brief(), difficulty="normal",
                capture=_capture([GOOD] * 3), react=react)
        out = buf.getvalue()
        self.assertEqual(len(shots), 3)            # the drill completes
        self.assertEqual(len(calls), 1)            # never retried after the death
        self.assertEqual(out.count("reaction API is unreachable"), 1)
        for s in shots:
            self.assertEqual(s.brain, "local")

    def test_dead_api_history_rows_are_local(self):
        def react(objection, rnd):
            raise OpenRouterError("boom")
        shots, _line = objection_llm.run_objection_llm_session(
            reps=2, seed=3, brief=_brief(), difficulty="normal",
            capture=_capture([GOOD] * 2), react=react)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "objection_llm_history.csv"
            objection_llm.append_objection_llm_history(path, "sess-1", shots,
                                                       difficulty="normal")
            with path.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames,
                                 objection_llm.OBJECTION_LLM_HISTORY_FIELDS)
                rows = list(reader)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["brain"] == "local" for r in rows))
        self.assertEqual([r["session"] for r in rows], ["sess-1", "sess-1"])

    def test_react_dying_mid_session_keeps_used_brain_per_round(self):
        state = {"n": 0}

        def react(objection, rnd):
            state["n"] += 1
            if state["n"] > 1:
                raise OpenRouterError("boom")
            return "Hmph. Bold of you."
        react.provider = "openrouter"

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, _line = objection_llm.run_objection_llm_session(
                reps=3, seed=4, brief=_brief(), difficulty="normal",
                capture=_capture([GOOD] * 3), react=react)
        self.assertEqual([s.brain for s in shots],
                         ["openrouter", "local", "local"])
        self.assertEqual(state["n"], 2)            # parked after the failure
        self.assertEqual(buf.getvalue().count("reaction API is unreachable"), 1)


class ScoringTests(unittest.TestCase):
    def test_canned_ack_question_response_scores(self):
        shots, _line = objection_llm.run_objection_llm_session(
            reps=1, seed=1, brief=_brief(), difficulty="normal",
            capture=_capture([GOOD]))
        s = shots[0]
        self.assertTrue(s.reflex)
        self.assertEqual(s.verdict, "HIT")         # text mode: no clock
        self.assertTrue(s.ack)
        self.assertTrue(s.question)
        self.assertIsNone(s.onset)
        self.assertEqual(s.response_text, GOOD)
        self.assertEqual(s.brief, "A1")

    def test_capability_pitch_is_miss_with_cooling_marker(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, _line = objection_llm.run_objection_llm_session(
                reps=1, seed=1, brief=_brief(), difficulty="normal",
                capture=_capture([PITCH]))
        s = shots[0]
        self.assertFalse(s.reflex)
        self.assertEqual(s.verdict, "MISS")
        self.assertFalse(s.ack)
        self.assertFalse(s.question)
        self.assertIn("cooling", buf.getvalue())


class ReactSeamTests(unittest.TestCase):
    def test_react_provider_stamps_brain_and_gets_round_and_objection(self):
        calls = []

        def react(objection, rnd):
            calls.append((objection, rnd))
            return "Look, we just don't have time for this."
        react.provider = "zai"

        shots, _line = objection_llm.run_objection_llm_session(
            reps=2, seed=2, brief=_brief(), difficulty="normal",
            capture=_capture([GOOD] * 2), react=react)
        self.assertEqual([s.brain for s in shots], ["zai", "zai"])
        self.assertEqual([c[1] for c in calls], [1, 2])
        self.assertEqual(calls[0][0], shots[0].objection)
        self.assertEqual(calls[1][0], shots[1].objection)

    def test_react_returning_nothing_stamps_local(self):
        def react(objection, rnd):
            return "   "
        react.provider = "openrouter"
        shots, _line = objection_llm.run_objection_llm_session(
            reps=1, seed=2, brief=_brief(), difficulty="normal",
            capture=_capture([GOOD]), react=react)
        self.assertEqual(shots[0].brain, "local")


class RunLiveTextModeTests(unittest.TestCase):
    def test_run_live_text_mode_writes_history_to_temp_sessions(self):
        # Voice path not tested (audio libs); this runs the real run_live in
        # --text mode with a dead reaction API to prove the whole live wiring:
        # banner, session, summary, one-time note, history into temp SESSIONS.
        inputs = iter(["", GOOD, GOOD, GOOD])      # ENTER, then 3 responses

        def fake_input(prompt=""):
            return next(inputs)

        def dead_react_factory(brief, provider, model_used, transport=None):
            def react(objection, rnd):
                raise OpenRouterError("boom")
            react.provider = provider
            return react

        args = types.SimpleNamespace(brief="A1", difficulty="normal", reps=3,
                                     seed=7, text=True, profile="generic_saas",
                                     buyer_provider="", llm_model=None)
        with tempfile.TemporaryDirectory() as tmp:
            old = objection_llm.SESSIONS
            objection_llm.SESSIONS = Path(tmp)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as buf, \
                        mock.patch("builtins.input", fake_input), \
                        mock.patch.object(objection_llm, "_make_react",
                                          dead_react_factory):
                    objection_llm.run_live(args)
            finally:
                objection_llm.SESSIONS = old

            out = buf.getvalue()
            self.assertEqual(out.count("reaction API is unreachable"), 1)
            self.assertIn("OBJECTION LLM", out)    # final summary line
            csv_path = Path(tmp) / "objection_llm_history.csv"
            with csv_path.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames,
                                 objection_llm.OBJECTION_LLM_HISTORY_FIELDS)
                rows = list(reader)
        self.assertEqual(len(rows), 3)
        row = rows[0]
        self.assertTrue(row["session"].endswith("-objection-llm"))
        self.assertEqual(row["round"], "1")
        self.assertEqual(row["brief"], "A1")
        self.assertEqual(row["difficulty"], "normal")
        self.assertEqual(row["ack"], "Y")
        self.assertEqual(row["question"], "Y")
        self.assertEqual(row["verdict"], "HIT")
        self.assertEqual(row["onset"], "")         # text mode: no clock
        self.assertEqual(row["response_text"], GOOD)
        self.assertEqual(row["brain"], "local")


if __name__ == "__main__":
    unittest.main()
