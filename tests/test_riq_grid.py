"""120-second RIQ prep-grid drill (--grid): offline seam tests.

The session core takes injected seams (capture, now), so the whole loop runs
without audio libs or a mic: seeded brief cycling, the six-element structure
grade, prep-verdict boundaries, the graceful EOF end of a rep set, and the
history CSV (written into a temp SESSIONS, swapped exactly like
tests/test_warmth.py swaps mock_call.SESSIONS). The voice path (ready gate,
Recorder, Transcriber) is not tested here — it is exercised only in live runs.

    .venv/Scripts/python.exe -m unittest tests.test_riq_grid -v
"""
from __future__ import annotations

import contextlib
import csv
import io
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import riq_briefs
import riq_grade
import riq_grid

A1 = riq_briefs.get_brief("A1")

# Adapted from the real Round-1 debrief A1 call: permissive opener, then the
# hook carrying R (memberships / flex passes) and I (most weekends, team of
# two), ending on the challenge question. Six of six.
STRONG = (
    "Hi Susie, I know you don't know me and this is a cold call out of the "
    "blue. Can I take thirty seconds to tell you why I called? If it's not "
    "for you, just say no and hang up and I'm gone. The reason I'm calling: "
    "season subscriptions are turning into memberships and flex passes "
    "across the sector. You've got productions running most weekends of the "
    "year and a team of two — how are you getting show-specific emails out "
    "to your past buyers without spending half your week exporting and "
    "cleaning lists?"
)

# The plan's weak delivery: leads with the platform, pitches capability,
# burns banned words, never asks anything.
WEAK = ("Actually, we have a great platform, our system gives you total "
        "visibility into your pipeline. It's a seamless solution.")

ELEMENT_KEYS = ["opener", "hook_r", "hook_i", "challenge", "question",
                "no_pitch"]


def _capture(responses, preps=None, durations=None):
    """Injected capture seam: capture() -> (text, prep_s, duration_s, froze)."""
    it = iter(responses)
    preps = iter(preps if preps is not None else [12.0] * len(responses))
    durations = iter(durations if durations is not None
                     else [None] * len(responses))
    calls = []

    def capture():
        calls.append(1)
        return next(it), next(preps), next(durations), False

    capture.calls = calls
    return capture


class GridScoreTests(unittest.TestCase):
    def test_strong_debrief_delivery_scores_six_of_six(self):
        passes, el = riq_grid.grid_score(STRONG, A1)
        self.assertEqual(passes, 6)
        self.assertTrue(all(el.values()), el)

    def test_weak_platform_pitch_scores_at_most_two(self):
        passes, el = riq_grid.grid_score(WEAK, A1)
        self.assertLessEqual(passes, 2)
        self.assertEqual(passes, 0)
        for key in ELEMENT_KEYS:
            self.assertFalse(el[key], key)

    def test_elements_have_the_six_fixed_keys(self):
        _passes, el = riq_grid.grid_score(STRONG, A1)
        self.assertEqual(list(el), ELEMENT_KEYS)

    def test_challenge_falls_back_to_implication_question(self):
        text = ("Season subscriptions are turning into memberships everywhere. "
                "When that email grind piles up mid-week, what does that cost "
                "you during on-sale season?")
        self.assertFalse(re.search(riq_grade.RIQ_CHALLENGE_RE, text.lower()))
        _passes, el = riq_grid.grid_score(text, A1)
        self.assertTrue(el["challenge"])
        self.assertTrue(el["question"])
        self.assertTrue(el["no_pitch"])

    def test_question_requires_the_delivery_to_end_on_the_question(self):
        text = ("How are you getting show-specific emails out without spending "
                "half your week exporting and cleaning lists? Honestly, that "
                "is the whole reason I called.")
        _passes, el = riq_grid.grid_score(text, A1)
        self.assertTrue(el["challenge"])
        self.assertFalse(el["question"])

    def test_empty_text_grades_only_no_pitch(self):
        # Literal spec: a silent/frozen delivery never pitched, so no_pitch
        # holds (not mentions_capability("")) while every structural element
        # fails — the plan empty-guards only the question element.
        passes, el = riq_grid.grid_score("", A1)
        self.assertEqual(passes, 1)
        self.assertTrue(el["no_pitch"])
        for key in ELEMENT_KEYS:
            if key != "no_pitch":
                self.assertFalse(el[key], key)


class RedactedCardTests(unittest.TestCase):
    def setUp(self):
        self.card = riq_grid.redacted_card(A1)

    def test_shows_the_four_allowed_fields(self):
        self.assertIn("Susie", self.card)                          # persona
        self.assertIn("marketing director", self.card)             # title
        self.assertIn("mid-size professional theatre", self.card)  # company_desc
        self.assertIn("productions most weekends of the year, a marketing "
                      "team of two", self.card)                    # internal_signal

    def test_redacts_challenge_hint_and_external_trigger(self):
        self.assertNotIn("sector-wide", self.card)                 # ext trigger
        self.assertNotIn("season ticket is becoming", self.card)
        self.assertNotIn("show-specific emails", self.card)        # challenge_hint
        self.assertNotIn("half your week", self.card)
        # and the rest of the brief stays hidden too
        self.assertNotIn("Constant Contact", self.card)            # status_quo
        self.assertNotIn("full day per campaign", self.card)       # pains
        self.assertNotIn("we're all set on email", self.card)      # objections

    def test_carries_the_instruction_line(self):
        self.assertIn("Build R (an industry pressure) + I (their signal) into "
                      "a challenge question. You have 120 seconds.", self.card)


class PrepVerdictTests(unittest.TestCase):
    def test_boundaries_fast_ok_slow(self):
        self.assertEqual(riq_grid.prep_verdict(0.0), "FAST")
        self.assertEqual(riq_grid.prep_verdict(59.9), "FAST")
        self.assertEqual(riq_grid.prep_verdict(60.0), "FAST")    # <= 60
        self.assertEqual(riq_grid.prep_verdict(60.1), "OK")
        self.assertEqual(riq_grid.prep_verdict(120.0), "OK")     # <= 120
        self.assertEqual(riq_grid.prep_verdict(120.1), "SLOW")
        self.assertEqual(riq_grid.prep_verdict(999.0), "SLOW")

    def test_no_clock_is_ok_never_hard_fail(self):
        # Text mode has no clock; prep never hard-fails a rep.
        self.assertEqual(riq_grid.prep_verdict(None), "OK")


class RunGridSessionTests(unittest.TestCase):
    def test_three_reps_cycle_distinct_briefs_via_seed(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, _summary = riq_grid.run_grid_session(
                reps=3, seed=11, brief_id="", text_mode=False,
                capture=_capture([STRONG, WEAK, STRONG]))
        self.assertEqual([s.index for s in shots], [1, 2, 3])
        self.assertEqual(len({s.brief_id for s in shots}), 3)    # no repeats
        self.assertTrue({s.brief_id for s in shots}
                        <= {b.id for b in riq_briefs.BRIEFS})

    def test_same_seed_same_brief_sequence(self):
        kw = dict(reps=3, seed=11, brief_id="", text_mode=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            a, _ = riq_grid.run_grid_session(capture=_capture([WEAK] * 3), **kw)
            b, _ = riq_grid.run_grid_session(capture=_capture([WEAK] * 3), **kw)
        self.assertEqual([s.brief_id for s in a], [s.brief_id for s in b])

    def test_pinned_brief_builds_all_three_with_prep_verdicts(self):
        capture = _capture([STRONG] * 3, preps=[10.0, 150.0, 45.0],
                           durations=[18.5, 20.0, 16.0])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, summary = riq_grid.run_grid_session(
                reps=3, seed=7, brief_id="A1", text_mode=False, capture=capture)
        self.assertEqual([s.brief_id for s in shots], ["A1"] * 3)
        self.assertEqual([s.passes for s in shots], [6, 6, 6])
        self.assertEqual([s.verdict for s in shots], ["FAST", "SLOW", "FAST"])
        self.assertEqual([s.prep_s for s in shots], [10.0, 150.0, 45.0])
        self.assertEqual([s.duration_s for s in shots], [18.5, 20.0, 16.0])
        self.assertEqual([s.text for s in shots], [STRONG] * 3)
        self.assertEqual(len(capture.calls), 3)
        self.assertIn("GRID  3/3 built", summary)
        self.assertIn("2 FAST", summary)
        self.assertIn("1 SLOW", summary)

    def test_weak_delivery_reports_missing_elements_and_banned_words(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, _summary = riq_grid.run_grid_session(
                reps=1, seed=1, brief_id="A1", text_mode=False,
                capture=_capture([WEAK]))
        shot = shots[0]
        self.assertFalse(shot.elements["no_pitch"])
        self.assertEqual(shot.banned, ["visibility", "solution", "seamless"])
        out = buf.getvalue()
        self.assertIn("missing:", out)
        self.assertIn("banned words:", out)
        self.assertIn("no_pitch", out)

    def test_banned_hit_does_not_flip_no_pitch(self):
        text = ("This is really about the list grind. What does that cost you "
                "in a week? Straight up, I want to give you visibility into "
                "your own numbers.")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, _summary = riq_grid.run_grid_session(
                reps=1, seed=1, brief_id="A1", text_mode=False,
                capture=_capture([text]))
        shot = shots[0]
        self.assertEqual(shot.banned, ["visibility"])
        self.assertTrue(shot.elements["no_pitch"])
        self.assertTrue(shot.elements["challenge"])

    def test_eof_ends_the_rep_set_gracefully(self):
        calls = []

        def capture():
            calls.append(1)
            if len(calls) == 2:
                raise riq_grid.RepSetDone("input pipe ran dry")
            return STRONG, 20.0, 15.0, False

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, summary = riq_grid.run_grid_session(
                reps=5, seed=3, brief_id="A1", text_mode=True, capture=capture)
        self.assertEqual(len(shots), 1)            # rep 2 never happened
        self.assertEqual(len(calls), 2)
        self.assertEqual(shots[0].index, 1)
        self.assertIn("GRID  1/1 built", summary)
        self.assertIn("ended early at 1/5", summary)

    def test_injected_now_drives_elapsed(self):
        ticks = iter([0.0, 250.0])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _shots, summary = riq_grid.run_grid_session(
                reps=1, seed=1, brief_id="A1", text_mode=False,
                capture=_capture([STRONG]), now=lambda: next(ticks))
        self.assertIn("elapsed 250s", summary)


class GridHistoryTests(unittest.TestCase):
    def _two_shots(self):
        capture = _capture([STRONG, WEAK], preps=[42.0, 130.0],
                           durations=[18.5, 12.0])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            shots, _summary = riq_grid.run_grid_session(
                reps=2, seed=5, brief_id="A1", text_mode=False, capture=capture)
        return shots

    def test_history_rows_written_to_temp_sessions(self):
        shots = self._two_shots()
        self.assertEqual(
            riq_grid.GRID_HISTORY_FIELDS,
            ["session", "rep", "brief", "prep_s", "passes", "opener",
             "hook_r", "hook_i", "challenge", "question", "no_pitch",
             "banned", "duration", "text"])
        with tempfile.TemporaryDirectory() as tmp:
            old = riq_grid.SESSIONS
            riq_grid.SESSIONS = Path(tmp)
            try:
                path = riq_grid.SESSIONS / riq_grid.GRID_HISTORY_NAME
                riq_grid.append_grid_history(path, "sess-grid-1", shots)
                riq_grid.append_grid_history(path, "sess-grid-2", shots)
            finally:
                riq_grid.SESSIONS = old
            with (Path(tmp) / riq_grid.GRID_HISTORY_NAME).open(
                    encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames,
                                 riq_grid.GRID_HISTORY_FIELDS)
                rows = list(reader)
        self.assertEqual(len(rows), 4)             # header written only once
        first = rows[0]
        self.assertEqual(first["session"], "sess-grid-1")
        self.assertEqual(first["rep"], "1")
        self.assertEqual(first["brief"], "A1")
        self.assertEqual(first["prep_s"], "42.0")
        self.assertEqual(first["passes"], "6")
        for key in ("opener", "hook_r", "hook_i", "challenge", "question",
                    "no_pitch"):
            self.assertEqual(first[key], "Y", key)
        self.assertEqual(first["banned"], "")
        self.assertEqual(first["duration"], "18.5")
        self.assertEqual(first["text"], STRONG)
        second = rows[1]
        self.assertEqual(second["prep_s"], "130.0")
        self.assertEqual(second["passes"], "0")
        self.assertEqual(second["no_pitch"], "N")
        self.assertEqual(second["banned"], "visibility|solution|seamless")
        self.assertEqual(second["duration"], "12.0")
        self.assertEqual(rows[2]["session"], "sess-grid-2")


class RunLiveTextModeTests(unittest.TestCase):
    def test_run_live_text_mode_writes_grid_history_to_temp_sessions(self):
        # Voice path not tested (audio libs); this runs the real run_live in
        # --text mode to prove the whole live wiring: banner, redacted card
        # per rep, per-rep verdict, final summary, history into temp SESSIONS.
        inputs = iter(["", STRONG, STRONG, STRONG])   # dial ENTER + 3 deliveries

        def fake_input(prompt=""):
            return next(inputs)

        args = types.SimpleNamespace(
            reps=3, seed=7, brief="A1", text=True, profile="generic_saas",
            device=None, silence=3.0, model="base.en",
        )
        with tempfile.TemporaryDirectory() as tmp:
            old = riq_grid.SESSIONS
            riq_grid.SESSIONS = Path(tmp)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as buf, \
                        mock.patch("builtins.input", fake_input):
                    riq_grid.run_live(args)
            finally:
                riq_grid.SESSIONS = old
            out = buf.getvalue()
            with (Path(tmp) / riq_grid.GRID_HISTORY_NAME).open(
                    encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames,
                                 riq_grid.GRID_HISTORY_FIELDS)
                rows = list(reader)
        self.assertIn("RIQ PREP GRID", out)            # banner
        self.assertIn("THEIR WORLD", out)              # card printed per rep
        self.assertNotIn("show-specific emails", out)  # card stays redacted
        self.assertIn("GRID  3/3 built", out)          # final summary line
        self.assertIn("prep is not timed", out)        # text-mode note
        self.assertEqual(len(rows), 3)
        row = rows[0]
        self.assertTrue(row["session"].endswith("-grid"))
        self.assertEqual(row["rep"], "1")
        self.assertEqual(row["brief"], "A1")
        self.assertEqual(row["passes"], "6")
        self.assertEqual(row["prep_s"], "")            # no clock in text mode
        self.assertEqual(row["duration"], "")
        self.assertEqual(row["text"], STRONG)


if __name__ == "__main__":
    unittest.main()
