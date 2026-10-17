"""RIQ grading: brief-scoped criteria + reuse of the grader's leak primitives."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader as G
import riq_briefs as B
import riq_grade as RG


def _turn(i, text, onset=0.8, duration=12.0, froze=False, pm_line=""):
    return G.Turn(index=i, stage_id="llm", expects="", pm_line=pm_line, text=text,
                  onset_latency=onset, duration=duration, internal_gaps=[],
                  is_objection=False, objection_label="", froze=froze)


GOOD = [
    _turn(1, "Hi Susie, this is Jason with AudienceView. I know I'm calling you "
            "out of the blue: do you have thirty seconds so I can tell you why I "
            "called, and then you can decide if we keep talking?"),
    _turn(2, "So the reason I'm calling: everywhere in the arts, season "
            "subscriptions are turning into memberships and flex passes. And I "
            "saw you've got productions running most weekends of the year with a "
            "team of two."),
    _turn(3, "With a team of two, how are you getting show-specific emails to "
            "your past buyers without spending half your week exporting and "
            "cleaning lists — what does that cost you?"),
    _turn(4, "By hand, every campaign. What happens the Monday your volunteer "
            "isn't here — who eats that work?"),
    _turn(5, "That's exactly why I'm calling. I'm not asking for anything today, "
            "but I've got data on how theatres like yours run this. Are you open "
            "to fifteen minutes Thursday at 10, or Friday at 2?"),
]
WEAK = [
    _turn(1, "Hi, is this Susie? Great. Our platform is the best solution on the "
            "market, full visibility into your campaigns."),
    _turn(2, "You can track everything automatically in one place."),
    _turn(3, "Anyway, I'll send you an email, let me know if sometime works."),
]
# R-only hook: carries A1's R terms but NO I terms (no 'team of two',
# 'most weekends', 'patron list') — for the brief-scoping test.
R_ONLY = _turn(2, "So the reason I'm calling: season subscriptions are turning "
                  "into memberships and flex passes everywhere. How does that "
                  "land on your pipeline this quarter?")


class RiqGradeTests(unittest.TestCase):
    def setUp(self):
        self.brief = B.get_brief("A1")

    def test_good_call_scores_all_five(self):
        rep = RG.grade_riq(GOOD, self.brief)
        self.assertEqual(rep.passed_count, 5)
        self.assertTrue(rep.verdict.startswith("YES"))
        by = {c.key: c.level for c in rep.criteria}
        self.assertEqual(by["riq_opener"], "STRONG")
        self.assertEqual(by["riq_hook"], "STRONG")      # R and I both matched
        self.assertEqual(by["riq_challenge"], "STRONG")
        self.assertEqual(by["riq_cta"], "STRONG")       # two specific times

    def test_low_friction_ask_is_pass_not_fail(self):
        # The playbook's Persona B / Elena close: one-page send, fifteen after.
        turns = GOOD[:4] + [_turn(5, "Can I send you the one-page breakdown of "
                                     "how other theatres solved this? If it "
                                     "resonates, we grab fifteen minutes after.")]
        rep = RG.grade_riq(turns, self.brief)
        cta = next(c for c in rep.criteria if c.key == "riq_cta")
        self.assertEqual(cta.level, "PASS")

    def test_weak_call_scores_low_no(self):
        rep = RG.grade_riq(WEAK, self.brief)
        self.assertLessEqual(rep.passed_count, 2)
        self.assertTrue(rep.verdict.startswith("NO"))

    def test_riq_terms_are_brief_scoped(self):
        rep = RG.grade_riq([GOOD[0], R_ONLY], self.brief)
        hook = next(c for c in rep.criteria if c.key == "riq_hook")
        self.assertEqual(hook.level, "PASS")
        self.assertIn("I not detected", hook.evidence)
        # and a generic SaaS hook matches nothing at all
        rep2 = RG.grade_riq([GOOD[0], _turn(2, "How are things on the pipeline "
                                                "this quarter?")], self.brief)
        hook2 = next(c for c in rep2.criteria if c.key == "riq_hook")
        self.assertEqual(hook2.level, "FAIL")

    def test_leaks_reused(self):
        rep = RG.grade_riq(GOOD, self.brief)
        keys = {lk.key for lk in rep.leaks}
        self.assertLessEqual({"filler_rate", "banned_words", "talk_time"}, keys)

    def test_history_row_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "llm_history.csv"
            rep = RG.grade_riq(GOOD, self.brief)
            RG.append_llm_history(path, "2026-10-15_test", rep, brief_id="A1",
                                  model="test-model", difficulty="normal")
            rows = list(csv.DictReader(path.open(encoding="utf-8")))
            self.assertEqual(rows[0]["brief"], "A1")
            self.assertEqual(rows[0]["criteria_passed"], "5")
            self.assertEqual(rows[0]["fallback"], "N")


class DebriefFixtureTests(unittest.TestCase):
    """Acceptance test for the whole stack: the REAL Round-1 debrief against
    Noell's Susie booked the meeting, so the deterministic grader must score
    it as a booked call. Its ask ("Thursday or Friday morning") counts via
    riq_time_offers' time-of-day detection; its challenge question matches
    CHALLENGE_RE. The call's doubled sentences and trial-offer close are
    imperfect on purpose — they must still book."""

    def test_real_round1_debrief_call_books(self):
        lines = [ln.strip()
                 for ln in (Path(__file__).resolve().parent / "data"
                            / "debrief_a1.txt").read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        self.assertEqual(len(lines), 8)
        turns = [_turn(i, text) for i, text in enumerate(lines, start=1)]
        rep = RG.grade_riq(turns, B.get_brief("A1"))
        self.assertGreaterEqual(rep.passed_count, 4)
        self.assertTrue(rep.verdict.startswith("YES"))


if __name__ == "__main__":
    unittest.main()
