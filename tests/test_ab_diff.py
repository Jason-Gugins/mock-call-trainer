"""Machine-readable per-rep transcripts (transcript.json) + ab_diff replay diff.

    .venv/Scripts/python.exe -m unittest tests.test_ab_diff -v

Covers both seams added in this task:
  - llm_call._persist / mock_call._persist write transcript.json inside the
    idempotence guard (at most once per rep).
  - ab_diff.py diffs two same-brief transcript.json files: criteria table with
    up/down arrows (STRONG > PASS > FAIL), leak deltas, beat-by-beat turn diff,
    --json machine output, actionable exit-2 errors.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ab_diff        # noqa: E402
import grader         # noqa: E402
import llm_call       # noqa: E402
import mock_call      # noqa: E402
import profiles       # noqa: E402
import riq_briefs     # noqa: E402


# --------------------------------------------------------------------------
# transcript.json fixtures (hand-written: ab_diff reads the file, not the app)
# --------------------------------------------------------------------------

STRONG_CRITERIA = {"riq_challenge": "STRONG", "riq_cta": "STRONG",
                   "riq_hook": "STRONG", "riq_listen": "STRONG",
                   "riq_opener": "STRONG"}
WEAKER_CRITERIA = dict(STRONG_CRITERIA, riq_cta="FAIL")

# (i, buyer pm_line, you said, onset, duration)
STRONG_BEATS = [
    (1, "Sure, make it quick, on-sale week.",
     "Hi Susie, this is Jason with AudienceView -- thirty seconds?", 0.6, 9.0),
    (2, "Honestly? I export and clean lists by hand.",
     "How are you getting show emails out without spending half your week "
     "cleaning lists?", 0.4, 11.0),
    (3, "The better part of a day, some weeks.",
     "Who eats that when it piles up -- you or the team?", 0.5, 8.0),
    (4, "Alright, Thursday works.",
     "Open to fifteen minutes Thursday at 10 or Friday at 2?", 0.3, 7.0),
]

STRONG_LEAKS = {"opener_latency": "0.6s", "filler_rate": "2 (0.6/100)",
                "banned_words": "0", "freezes": "none", "talk_time": "35s"}
WEAKER_LEAKS = dict(STRONG_LEAKS, filler_rate="6 (1.8/100)", talk_time="28s")


def _turns(beats, drop_from=None):
    """Beats -> the interleaved buyer/you turn entries transcript.json stores."""
    out = []
    for i, pm, you, onset, duration in beats:
        if drop_from is not None and i >= drop_from:
            continue
        out.append({"i": i, "who": "buyer", "text": pm})
        out.append({"i": i, "who": "you", "text": you,
                    "onset": onset, "duration": duration})
    return out


def _transcript(session, criteria, beats, leaks, verdict, kind="llm",
                brief="A1", model="fake/model", fallback=False):
    return {"session": session, "kind": kind, "brief": brief,
            "difficulty": "normal", "model": model, "fallback": fallback,
            "criteria": criteria, "leaks": leaks, "verdict": verdict,
            "turns": _turns(beats)}


def _write_side(root, name, data):
    d = root / name
    d.mkdir(parents=True)
    (d / "transcript.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def _strong():
    return _transcript("s-strong", STRONG_CRITERIA, STRONG_BEATS, STRONG_LEAKS,
                       "YES -- RIQ executed.")


def _weaker():
    beats = STRONG_BEATS[:3]                       # hangs up after turn 3
    return _transcript("s-weaker", WEAKER_CRITERIA, beats, WEAKER_LEAKS,
                       "NOT YET -- the ask slipped.")


def _run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ab_diff.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------
# Pure diff helpers
# --------------------------------------------------------------------------

class CriteriaDiffTests(unittest.TestCase):
    def test_rows_sorted_by_key(self):
        rows = ab_diff.diff_criteria(_strong(), _weaker())
        self.assertEqual([r["key"] for r in rows], sorted(STRONG_CRITERIA))

    def test_regression_is_down_arrow(self):
        rows = ab_diff.diff_criteria(_strong(), _weaker())
        cta = next(r for r in rows if r["key"] == "riq_cta")
        self.assertEqual(cta, {"key": "riq_cta", "a": "STRONG", "b": "FAIL",
                               "change": "v"})

    def test_improvement_is_up_arrow_and_same_is_equals(self):
        up = ab_diff.diff_criteria(_weaker(), _strong())
        self.assertEqual(next(r for r in up if r["key"] == "riq_cta")["change"],
                         "^")
        same = ab_diff.diff_criteria(_strong(), _strong())
        self.assertEqual(next(r for r in same if r["key"] == "riq_cta")["change"],
                         "=")

    def test_unknown_or_missing_level_is_question_mark(self):
        odd = dict(STRONG_CRITERIA, riq_hook="MEH")
        rows = ab_diff.diff_criteria(_transcript("a", odd, STRONG_BEATS,
                                                 STRONG_LEAKS, "v"), _strong())
        self.assertEqual(next(r for r in rows if r["key"] == "riq_hook")["change"],
                         "?")
        one_sided = {"riq_opener": "PASS"}         # key missing on side B
        rows = ab_diff.diff_criteria(
            _transcript("a", one_sided, [], {}, "v"),
            _transcript("b", {"riq_hook": "PASS"}, [], {}, "v"))
        self.assertEqual(next(r for r in rows if r["key"] == "riq_opener")["change"],
                         "?")


class LeakDiffTests(unittest.TestCase):
    def test_shared_keys_only_and_changed_flag(self):
        rows = ab_diff.diff_leaks(_strong(), _weaker())
        by_key = {r["key"]: r for r in rows}
        self.assertEqual(by_key["filler_rate"],
                         {"key": "filler_rate", "a": "2 (0.6/100)",
                          "b": "6 (1.8/100)", "changed": True})
        self.assertEqual(by_key["opener_latency"]["changed"], False)

    def test_key_present_on_one_side_only_is_omitted(self):
        a = _transcript("a", STRONG_CRITERIA, [], {"only_a": "x"}, "v")
        rows = ab_diff.diff_leaks(a, _strong())
        self.assertNotIn("only_a", {r["key"] for r in rows})


class TurnDiffTests(unittest.TestCase):
    def test_missing_turn_is_divergent(self):
        rows = ab_diff.diff_turns(_strong(), _weaker())
        self.assertEqual([r["i"] for r in rows], [1, 2, 3, 4])
        last = rows[-1]
        self.assertTrue(last["divergent"])
        self.assertEqual(last["a"], STRONG_BEATS[3][2])
        self.assertIsNone(last["b"])

    def test_aligned_turns_share_the_buyer_prompt(self):
        rows = ab_diff.diff_turns(_strong(), _weaker())
        self.assertEqual(rows[0]["buyer"], STRONG_BEATS[0][1])
        self.assertFalse(rows[0]["divergent"])

    def test_length_divergence_threshold_is_40_percent(self):
        def side(session, text):
            return _transcript(session, STRONG_CRITERIA,
                               [(1, "pm", text, 0.5, 9.0)], {}, "v")
        base = "x" * 100
        self.assertTrue(ab_diff.diff_turns(side("a", base),
                                           side("b", "x" * 59))[0]["divergent"])
        # Exactly 40% shorter is NOT divergent (>40% is the rule).
        self.assertFalse(ab_diff.diff_turns(side("a", base),
                                            side("b", "x" * 60))[0]["divergent"])
        self.assertFalse(ab_diff.diff_turns(side("a", base),
                                            side("b", "x" * 75))[0]["divergent"])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class AbDiffCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.dir_a = _write_side(root, "a", _strong())
        self.dir_b = _write_side(root, "b", _weaker())

    def test_happy_path_exit_0_pretty_output(self):
        code, out, _ = _run_cli(self.dir_a, self.dir_b)
        self.assertEqual(code, 0)
        self.assertIn("s-strong", out)
        self.assertIn("s-weaker", out)
        self.assertIn("A1", out)
        self.assertIn("CRITERION", out)
        self.assertIn("riq_cta", out)

    def test_criteria_table_marks_the_regression(self):
        _, out, _ = _run_cli(self.dir_a, self.dir_b)
        line = next(ln for ln in out.splitlines() if "riq_cta" in ln)
        self.assertRegex(line, r"STRONG\s+FAIL\s+v\s*$")
        # Reversed: the same delta is an improvement (up arrow).
        _, out, _ = _run_cli(self.dir_b, self.dir_a)
        line = next(ln for ln in out.splitlines() if "riq_cta" in ln)
        self.assertRegex(line, r"FAIL\s+STRONG\s+\^\s*$")

    def test_turn_diff_flags_the_missing_turn(self):
        _, out, _ = _run_cli(self.dir_a, self.dir_b)
        self.assertIn("<< divergent >>", out)
        # The buyer prompt comes from side A, once per turn.
        self.assertIn("Open to fifteen minutes Thursday at 10 or Friday at 2?",
                      out)

    def test_json_top_level_keys_exactly(self):
        code, out, _ = _run_cli(self.dir_a, self.dir_b, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(set(data), {"a", "b", "criteria", "leaks", "turns"})

    def test_json_meta_carries_both_sides(self):
        _, out, _ = _run_cli(self.dir_a, self.dir_b, "--json")
        data = json.loads(out)
        self.assertEqual(data["a"]["session"], "s-strong")
        self.assertEqual(data["b"]["session"], "s-weaker")
        for meta in (data["a"], data["b"]):
            self.assertEqual(set(meta), {"session", "kind", "brief",
                                         "difficulty", "model", "fallback",
                                         "summary"})
        self.assertEqual(data["a"]["summary"], 5)      # all STRONG
        self.assertEqual(data["b"]["summary"], 4)      # riq_cta FAILs

    def test_json_row_shapes(self):
        _, out, _ = _run_cli(self.dir_a, self.dir_b, "--json")
        data = json.loads(out)
        for row in data["criteria"]:
            self.assertEqual(set(row), {"key", "a", "b", "change"})
        for row in data["leaks"]:
            self.assertEqual(set(row), {"key", "a", "b", "changed"})
        for row in data["turns"]:
            self.assertEqual(set(row), {"i", "buyer", "a", "b", "divergent"})
        cta = next(r for r in data["criteria"] if r["key"] == "riq_cta")
        self.assertEqual(cta["change"], "v")
        self.assertTrue(data["turns"][-1]["divergent"])
        self.assertEqual(data["turns"][-1]["i"], 4)
        self.assertIsNone(data["turns"][-1]["b"])

    def test_json_leaks_mark_changed(self):
        _, out, _ = _run_cli(self.dir_a, self.dir_b, "--json")
        leaks = {r["key"]: r["changed"] for r in json.loads(out)["leaks"]}
        self.assertEqual(leaks, {"opener_latency": False, "filler_rate": True,
                                 "banned_words": False, "freezes": False,
                                 "talk_time": True})

    def test_missing_dir_exits_2_with_actionable_message(self):
        code, _, err = _run_cli(self.dir_a / "nope", self.dir_b)
        self.assertEqual(code, 2)
        self.assertIn("nope", err)

    def test_dir_without_transcript_exits_2(self):
        empty = Path(self._tmp.name) / "empty"
        empty.mkdir()
        code, _, err = _run_cli(empty, self.dir_b)
        self.assertEqual(code, 2)
        self.assertIn("transcript.json", err)


# --------------------------------------------------------------------------
# _persist writes transcript.json (inside the idempotence guard)
# --------------------------------------------------------------------------

class PersistTranscriptTests(unittest.TestCase):
    def _llm_state(self):
        turns = [grader.Turn(index=i, stage_id="llm", expects="", pm_line=pm,
                             text=said, onset_latency=onset, duration=dur,
                             internal_gaps=[], is_objection=False,
                             objection_label="", froze=False)
                 for i, pm, said, onset, dur in STRONG_BEATS[:2]]
        return llm_call.LlmCallState(turns=turns, model="fake/model",
                                     fallback=False)

    def _offline_state(self):
        turns = [grader.Turn(index=1, stage_id="opener", expects="",
                             pm_line="Go ahead.", text="Hi, is this Mike? "
                             "Do you handle submittals by hand today?",
                             onset_latency=0.5, duration=9.0),
                 grader.Turn(index=2, stage_id="probe", expects="",
                             pm_line="Mostly, yes.", text="What does that "
                             "cost you every week?", onset_latency=0.4,
                             duration=7.0)]
        return mock_call.CallState(turns=turns)

    def test_llm_persist_writes_transcript_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = llm_call.SESSIONS
            llm_call.SESSIONS = Path(tmp)
            try:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    llm_call._persist(Path(tmp) / "s1", "s1", self._llm_state(),
                                      riq_briefs.get_brief("A1"),
                                      types.SimpleNamespace(difficulty="normal"),
                                      text_mode=True)
            finally:
                llm_call.SESSIONS = old
            data = json.loads((Path(tmp) / "s1" / "transcript.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(data["session"], "s1")
        self.assertEqual(data["kind"], "llm")
        self.assertEqual(data["brief"], "A1")
        self.assertEqual(data["difficulty"], "normal")
        self.assertEqual(data["model"], "fake/model")
        self.assertFalse(data["fallback"])
        self.assertEqual(set(data["criteria"]),
                         {"riq_opener", "riq_hook", "riq_challenge",
                          "riq_cta", "riq_listen"})
        self.assertEqual(set(data["leaks"]),
                         {"opener_latency", "filler_rate", "banned_words",
                          "freezes", "talk_time"})
        self.assertIn(data["verdict"][:3], ("YES", "NOT", "NO "))
        self.assertEqual(len(data["turns"]), 4)        # 2 turns x (buyer, you)
        self.assertEqual(data["turns"][0],
                         {"i": 1, "who": "buyer", "text": STRONG_BEATS[0][1]})
        you = data["turns"][1]
        self.assertEqual(you["who"], "you")
        self.assertEqual(you["text"], STRONG_BEATS[0][2])
        self.assertEqual(you["onset"], 0.6)
        self.assertEqual(you["duration"], 9.0)
        self.assertNotIn("onset", data["turns"][0])

    def test_llm_persist_transcript_stays_inside_idempotence_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = llm_call.SESSIONS
            llm_call.SESSIONS = Path(tmp)
            state = self._llm_state()
            outdir = Path(tmp) / "s1"
            args = types.SimpleNamespace(difficulty="normal")
            try:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    llm_call._persist(outdir, "s1", state,
                                      riq_briefs.get_brief("A1"), args,
                                      text_mode=True)
                (outdir / "transcript.json").unlink()
                with redirect_stdout(out), redirect_stderr(err):
                    llm_call._persist(outdir, "s1", state,
                                      riq_briefs.get_brief("A1"), args,
                                      text_mode=True)
            finally:
                llm_call.SESSIONS = old
            self.assertFalse((outdir / "transcript.json").exists())

    def test_offline_persist_writes_transcript_json(self):
        profile = profiles.get_profile("generic_saas")
        with tempfile.TemporaryDirectory() as tmp:
            old = mock_call.SESSIONS
            mock_call.SESSIONS = Path(tmp)
            outdir = Path(tmp) / "s2"
            outdir.mkdir()                         # run_call creates it pre-call
            try:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    mock_call._persist(outdir, "s2", self._offline_state(),
                                       types.SimpleNamespace(difficulty="normal",
                                                             text=True),
                                       profile, text_mode=True)
            finally:
                mock_call.SESSIONS = old
            data = json.loads((Path(tmp) / "s2" / "transcript.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(data["session"], "s2")
        self.assertEqual(data["kind"], "offline")
        self.assertEqual(data["brief"], profile.name)
        self.assertEqual(data["model"], "")
        self.assertFalse(data["fallback"])
        self.assertEqual(set(data["criteria"]),
                         {"c1_industry_language", "c2_targeted_questions",
                          "c3_uncover_pain", "c4_book_followup",
                          "c5_handle_objections"})
        self.assertTrue(data["leaks"])                 # wave-1 leak metrics
        self.assertEqual(len(data["turns"]), 4)
        self.assertEqual(data["turns"][0],
                         {"i": 1, "who": "buyer", "text": "Go ahead."})
        self.assertEqual(data["turns"][1]["who"], "you")
        self.assertIn("submittals", data["turns"][1]["text"])
        self.assertNotIn("onset", data["turns"][0])

    def test_offline_persist_transcript_stays_inside_idempotence_guard(self):
        profile = profiles.get_profile("generic_saas")
        with tempfile.TemporaryDirectory() as tmp:
            old = mock_call.SESSIONS
            mock_call.SESSIONS = Path(tmp)
            state = self._offline_state()
            outdir = Path(tmp) / "s2"
            outdir.mkdir()                         # run_call creates it pre-call
            args = types.SimpleNamespace(difficulty="normal", text=True)
            try:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    mock_call._persist(outdir, "s2", state, args, profile,
                                       text_mode=True)
                (outdir / "transcript.json").unlink()
                with redirect_stdout(out), redirect_stderr(err):
                    mock_call._persist(outdir, "s2", state, args, profile,
                                       text_mode=True)
            finally:
                mock_call.SESSIONS = old
            self.assertFalse((outdir / "transcript.json").exists())


if __name__ == "__main__":
    unittest.main()
