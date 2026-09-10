"""Unit tests for pain-reveal drill scoring. No audio, no pytest."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import grader as G
import persona as P


class ScoreDrillShot(unittest.TestCase):
    def test_cost_question_fast(self):
        hit, verdict = G.score_drill_shot(
            "And what did that cost you? Did it come out of your float?",
            onset=2.8, froze=False,
        )
        self.assertTrue(hit)
        self.assertEqual(verdict, "FAST")

    def test_cost_question_ok_band(self):
        hit, verdict = G.score_drill_shot(
            "Who ate that, you or the owner?", onset=4.9, froze=False,
        )
        self.assertTrue(hit)
        self.assertEqual(verdict, "OK")

    def test_cost_question_slow_still_counts(self):
        hit, verdict = G.score_drill_shot(
            "Who ate that — you or the owner?", onset=11.1, froze=False,
        )
        self.assertTrue(hit)
        self.assertEqual(verdict, "SLOW")

    def test_walk_me_through_is_miss(self):
        hit, verdict = G.score_drill_shot(
            "Walk me through it. How did that happen?", onset=1.0, froze=False,
        )
        self.assertFalse(hit)
        self.assertEqual(verdict, "MISS")

    def test_close_instead_of_cost_is_miss(self):
        hit, verdict = G.score_drill_shot(
            "I'd love to book 20 minutes Thursday at 7.", onset=0.4, froze=False,
        )
        self.assertFalse(hit)
        self.assertEqual(verdict, "MISS")

    def test_sympathy_is_miss(self):
        hit, verdict = G.score_drill_shot(
            "Yeah that sucks, that makes sense.", onset=0.5, froze=False,
        )
        self.assertFalse(hit)
        self.assertEqual(verdict, "MISS")

    def test_freeze_is_miss(self):
        hit, verdict = G.score_drill_shot("", onset=None, froze=True)
        self.assertFalse(hit)
        self.assertEqual(verdict, "MISS")

    def test_text_mode_no_clock(self):
        hit, verdict = G.score_drill_shot(
            "What does that do to your holdback release?", onset=None, froze=False,
        )
        self.assertTrue(hit)
        self.assertEqual(verdict, "HIT")

    def test_bank_lines_all_hit(self):
        bank = [
            "A week of tear-out on Dundas — who ate that, you or the owner?",
            "Did that week come out of your float, or did it push substantial completion?",
            "Three weeks on every job — is that your evenings and weekends, or is it holding up the final billing?",
            "What does that do to your holdback release?",
            "When one gets built before it's signed, does that come out of your fee or the project contingency?",
            "How often does the owner just refuse to pay it?",
            "When an RFI sits two weeks, is the crew standing around, or building ahead and hoping?",
            "How far do they usually get before somebody notices?",
        ]
        for line in bank:
            hit, verdict = G.score_drill_shot(line, onset=2.0, froze=False)
            self.assertTrue(hit, msg=line)
            self.assertEqual(verdict, "FAST", msg=line)


class PainCues(unittest.TestCase):
    def test_ten_cues_rotate_and_are_short(self):
        lines = P.pain_drill_cues(n=10, rng=__import__("random").Random(0))
        self.assertEqual(len(lines), 10)
        self.assertEqual(len(set(lines)), len(P.PAIN_DRILL_CUES))
        for line in lines:
            self.assertLessEqual(len(line.split()), 40)
            self.assertTrue(line.strip())

    def test_full_call_pain_unchanged(self):
        self.assertEqual(len(P.PAIN_REVEAL), 3)
        self.assertTrue(any("Dundas" in s for s in P.PAIN_REVEAL))


class SummarizeDrill(unittest.TestCase):
    def test_counts(self):
        shots = [
            G.DrillShot(1, "cue", "Who ate that?", 2.8, False, True, "FAST"),
            G.DrillShot(2, "cue", "Walk me through it.", 1.0, False, False, "MISS"),
            G.DrillShot(3, "cue", "Who ate that?", 11.1, False, True, "SLOW"),
        ]
        s = G.summarize_drill(shots, elapsed_s=47.0, reps_requested=10)
        self.assertEqual(s.hits, 2)
        self.assertEqual(s.n, 3)
        self.assertEqual(s.fast, 1)
        self.assertEqual(s.miss, 1)
        self.assertAlmostEqual(s.median_onset, 6.95, places=2)
        self.assertEqual(
            s.line,
            "DRILL  2/3 cost questions  median 6.9s  (1 FAST, 0 OK, 1 SLOW, 1 MISS)",
        )

    def test_csv_does_not_touch_full_call_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            shots = [
                G.DrillShot(1, "cue-a", "Who ate that?", 2.8, False, True, "FAST"),
                G.DrillShot(2, "cue-b", "Walk me through it.", 1.0, False, False, "MISS"),
            ]
            G.append_drill_history(folder / "drill_history.csv", "sess1", shots, 12.0)
            with (folder / "drill_history.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["verdict"], "FAST")
            self.assertEqual(rows[1]["cost_question"], "N")
            self.assertFalse((folder / "history.csv").exists())


class DrillLoop(unittest.TestCase):
    def test_stops_at_ten(self):
        import drill
        answers = [
            ("Who ate that, you or the owner?", 2.0, False)
        ] * 15
        it = iter(answers)
        shots, summary = drill.run_drill_session(
            reps=10, minutes=3, seed=0, text_mode=True,
            capture=lambda: next(it),
            now=lambda: 0.0,
        )
        self.assertEqual(len(shots), 10)
        self.assertEqual(summary.hits, 10)

    def test_budget_cuts_the_set(self):
        import drill
        clock = {"t": 0.0}

        def now():
            return clock["t"]

        def capture():
            clock["t"] += 70.0
            return ("Who ate that, you or the owner?", 2.0, False)

        shots, summary = drill.run_drill_session(
            reps=10, minutes=3, seed=0, text_mode=True,
            capture=capture, now=now,
        )
        self.assertEqual(len(shots), 3)
        self.assertEqual(summary.elapsed_s, 210.0)


class RenderDrill(unittest.TestCase):
    def test_markdown_has_summary_and_shots(self):
        shots = [
            G.DrillShot(1, "cue-a", "Who ate that?", 2.8, False, True, "FAST"),
            G.DrillShot(2, "cue-b", "Walk me through it.", 1.0, False, False, "MISS"),
        ]
        s = G.summarize_drill(shots, 20.0, 10)
        md = G.render_drill_markdown(s, shots, "2026-08-20_195400-drill", "")
        self.assertIn("1/2", md)
        self.assertIn("FAST", md)
        self.assertIn("Who ate that?", md)
        self.assertNotIn("PROCORE'S FIVE", md)
        self.assertNotIn("WOULD REENA", md)


class CliDrill(unittest.TestCase):
    """Runs the real CLI, so MOCKCALL_SESSIONS is redirected at a temp dir.

    Without that these tests append fake rows to the real drill_history.csv and
    leave junk session folders next to the recorded reps.
    """

    def _run(self, argv, stdin, sessions):
        import os
        import subprocess
        root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        env["MOCKCALL_SESSIONS"] = str(sessions)
        return subprocess.run(
            [sys.executable, str(root / "mock_call.py"), *argv],
            input=stdin, text=True, cwd=str(root), capture_output=True,
            timeout=60, env=env,
        )

    def test_text_drill_three_shots(self):
        answers = (
            "Who ate that, you or the owner?\n"
            "Walk me through it.\n"
            "What does that do to your holdback release?\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(["--drill", "--text", "--reps", "3"], "\n" + answers, tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("DRILL", proc.stdout)
            self.assertIn("2/3", proc.stdout)
            self.assertNotIn("PROCORE'S FIVE PUBLISHED CRITERIA", proc.stdout)
            # and it wrote where we told it to, not into the real sessions dir
            self.assertTrue((Path(tmp) / "drill_history.csv").exists())

    def test_paraphrase_cli_rejects_a_repeat(self):
        line = ("Total stranger calling out of the blue here. Can you spare me "
                "twenty seconds before you write me off?")
        stdin = "\n" + line + "\n" + line + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(
                ["--paraphrase", "--beat", "opener", "--text", "--reps", "2"],
                stdin, tmp,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("FRESH", proc.stdout)
            self.assertIn("RECITED", proc.stdout)
            self.assertIn("1/2 fresh", proc.stdout)
            # bank is keyed by the active profile (generic_saas is the default)
            self.assertTrue((Path(tmp) / "paraphrase_bank_generic_saas.json").exists())

    def test_real_sessions_dir_untouched_by_tests(self):
        """Guard against this whole class regressing and eating live data again."""
        root = Path(__file__).resolve().parent.parent
        before = {p.name for p in (root / "sessions").iterdir()}
        with tempfile.TemporaryDirectory() as tmp:
            self._run(["--drill", "--text", "--reps", "1"], "\nWho ate that?\n", tmp)
        after = {p.name for p in (root / "sessions").iterdir()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
