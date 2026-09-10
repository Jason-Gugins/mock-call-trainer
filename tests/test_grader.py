"""Direct unit tests for the core rubric grader.

test_drill and test_paraphrase cover the drill branches and test_pipeline
checks real speech -> grader agreement, but nothing exercises `grader.grade()`
itself: the five criteria, the leak metrics, and the verdict. This locks that
behaviour down so a rubric change can't silently reorder the verdict.

    .venv/Scripts/python.exe tests/test_grader.py
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader as G
import persona as P   # noqa: E402


def _turn(index, stage_id, text, onset, is_objection, label,
          duration=10.0, expects="", pm_line=""):
    return G.Turn(
        index=index, stage_id=stage_id, expects=expects, pm_line=pm_line,
        text=text, onset_latency=onset, duration=duration,
        internal_gaps=[], is_objection=is_objection,
        objection_label=label, froze=False,
    )


# Stage ids / objection flags are order-fixed regardless of the rng seed.
STAGES = [(s.id, s.is_objection, s.objection_label)
          for s in P.build_script("normal", random.Random(0))]


def build_good():
    texts = [
        "Mike, I'll be straight with you, you don't know me and I'm jumping "
        "right into the middle of your day. Can I take thirty seconds to tell "
        "you why I called, and if it's not for you, just tell me and I'm gone?",
        "I've been talking with senior PMs at general contractors around here "
        "and the same thing keeps coming up. When a change order or an RFI "
        "can't be found fast enough, the crews running on paper get caught "
        "out. Is that playing out on your jobs?",
        "Thirty years, that's no fluke, and I'm not going to tell you paper's "
        "the problem. When a drawing gets revised, how do you know the field "
        "isn't still on the superseded set?",
        "Walk me through it. When the architect issues a revision mid-job, "
        "how does the crew in the field find out?",
        "Yeah, that tracks. When a change order gets built before it's signed "
        "off, who eats that cost?",
        "I won't pretend it doesn't happen. Almost every time it's because "
        "the office handed the foreman a login with no reason to open it. Was "
        "it the tool itself, or the way it got rolled out?",
        "You're right, if the field won't touch it it's dead. The ones that "
        "stick start on one job with real training. Does that sound closer "
        "to what you'd need?",
        "Yeah, I can do that. But I'll be honest, my email gets buried. Would "
        "Thursday at 7 before the crews roll, or Friday at 4 after your job "
        "walk, be easier for twenty minutes with our AE?",
        "Thursday at 7 it is. What's the best email for the invite? I'll put "
        "a note on it so he comes ready to talk change orders and closeout.",
    ]
    turns = []
    for i, (sid, is_obj, label) in enumerate(STAGES, start=1):
        onset = 0.8
        if i == 1:
            onset = 0.2          # fast opener
        turns.append(_turn(i, sid, texts[i - 1], onset, is_obj, label))
    return turns


def build_weak():
    texts = [
        "Hi is this Mike? My name is Jason and I'm calling from Procore, "
        "we're a construction management software platform and I wanted to "
        "tell you about what we do.",
        "So Procore is a solution that gives you complete visibility across "
        "all your projects and helps you streamline your workflows.",
        "But actually paper is really inefficient. Our platform can "
        "automatically track everything for you in one place.",
        "It's honestly a game-changer. You can see all your documents in "
        "real time and our dashboard is best-in-class.",
        "Right, so our solution would fix that for you completely.",
        "Well our software is different, it's much more robust and seamless "
        "than whatever you had before.",
        "We leverage best-in-class technology and it's a very holistic "
        "platform.",
        "Sure, I'll send you an email with some information.",
        "Okay, thanks a lot.",
    ]
    turns = []
    for i, (sid, is_obj, label) in enumerate(STAGES, start=1):
        turns.append(_turn(i, sid, texts[i - 1], 4.0, is_obj, label))
    return turns


class GradeGood(unittest.TestCase):
    def setUp(self):
        self.good = build_good()

    def test_five_of_five_and_yes(self):
        rep = G.grade(self.good, "normal", pain_revealed=True, meeting_booked=True)
        self.assertEqual(rep.passed_count, 5)
        self.assertTrue(rep.verdict.startswith("YES"))

    def test_close_booked_two_times_strong(self):
        rep = G.grade(self.good, "normal", True, True)
        c4 = next(c for c in rep.criteria if c.key == "c4_book_followup")
        self.assertEqual(c4.level, G.STRONG)

    def test_no_leaks(self):
        rep = G.grade(self.good, "normal", True, True)
        v = {lk.key: lk.verdict for lk in rep.leaks}
        self.assertEqual(v["opener_latency"], "GOOD")
        self.assertEqual(v["ack_rate"], "GOOD")
        self.assertTrue(v["pitch_before_pain"].startswith("GOOD"))
        self.assertTrue(v["banned_words"].startswith("GOOD"))


class GradeWeak(unittest.TestCase):
    def setUp(self):
        self.weak = build_weak()

    def test_zero_of_five_and_no(self):
        rep = G.grade(self.weak, "normal", pain_revealed=False, meeting_booked=False)
        self.assertEqual(rep.passed_count, 0)
        self.assertTrue(rep.verdict.startswith("NO"))

    def test_pitch_before_pain_leak(self):
        rep = G.grade(self.weak, "normal", False, False)
        pbp = next(lk for lk in rep.leaks if lk.key == "pitch_before_pain")
        self.assertTrue(pbp.verdict.startswith("LEAK"))

    def test_opener_latency_leak(self):
        rep = G.grade(self.weak, "normal", False, False)
        ol = next(lk for lk in rep.leaks if lk.key == "opener_latency")
        self.assertEqual(ol.verdict, "LEAK")


class GradeGeneric(unittest.TestCase):
    """c1 vocabulary is profile-driven; procore stays the default for back-compat."""

    def setUp(self):
        import profiles
        self.gen = profiles.get_profile("generic_saas")
        self.pro = profiles.get_profile("procore")

    def test_default_profile_is_procore(self):
        # No profile argument -> procore behaviour preserved.
        rep = G.grade(build_good(), "normal", True, True)
        self.assertEqual(rep.passed_count, 5)
        self.assertTrue(rep.verdict.startswith("YES"))

    def test_saas_terms_feed_generic_c1(self):
        text = ("our pipeline is stuffed with dead leads, the crm is full of churn, "
                "forecast is off, and none of our demos convert to revenue.")
        gen = G.find_matches(text, self.gen.high_value_terms)
        pro = G.find_matches(text, self.pro.high_value_terms)
        self.assertGreaterEqual(len(gen), 4)   # pipeline, lead, crm, churn, forecast, demo...
        self.assertEqual(len(pro), 0)          # construction terms absent

    def test_construction_terms_feed_procore_c1(self):
        text = ("RFIs and submittals sit in the truck, the change order got superseded, "
                "closeout is a mess and the daily log is never current.")
        pro = G.find_matches(text, self.pro.high_value_terms)
        gen = G.find_matches(text, self.gen.high_value_terms)
        self.assertGreaterEqual(len(pro), 5)
        self.assertEqual(len(gen), 0)

    def test_procore_c1_missed_keeps_original_priority(self):
        # regression: the coaching "Missed high-value" list must use the profile's
        # c1_priority (original six incl. closeout), not a dict-insertion-order slice.
        empty_turn = G.Turn(1, "pickup", "x", "", "", onset_latency=0.5)
        rep = G.grade([empty_turn], "normal", True, True, profile=self.pro)
        c1 = next(c for c in rep.criteria if c.key == "c1_industry_language")
        self.assertIn("closeout", c1.evidence)
        self.assertNotIn("as-built", c1.evidence)


if __name__ == "__main__":
    unittest.main()
