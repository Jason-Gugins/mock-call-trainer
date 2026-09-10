"""Progress aggregation, trend, coaching, and the report CLI. Uses trend's parsers."""
from __future__ import annotations
import csv, sys, tempfile, unittest, unittest.mock as mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import progress as P


def _write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


class Series(unittest.TestCase):
    def test_full(self):
        rows = [{"criteria_passed": "4", "opener_latency": "1.7s", "ack_rate": "66%",
                 "filler_rate": "2 in 349 words (0.6/100)"},
                {"criteria_passed": "5", "opener_latency": "0.2s", "ack_rate": "100%",
                 "filler_rate": "7 in 480 words (1.5/100)"}]
        s = P.full_series(rows)
        self.assertEqual(s["criteria/5"], [4, 5])
        self.assertEqual(s["opener_latency_s"], [1.7, 0.2])
        self.assertEqual(s["ack_rate_%"], [66, 100])
        self.assertEqual(s["filler_rate_per100"], [0.6, 1.5])   # rate, not count

    def test_objection(self):
        rows = [{"verdict": "FAST", "reflex": "Y", "onset": "1.0"},
                {"verdict": "MISS", "reflex": "Y", "onset": "0.5"},
                {"verdict": "OK", "reflex": "N", "onset": "3.0"}]
        s = P.objection_series(rows)
        self.assertEqual(s["reflex_%"], [100, 100, 0])
        self.assertEqual(s["median_onset_s"], [1.0, 0.5, 3.0])
        self.assertEqual(s["obj_ok_fast_%"], [100, 0, 100])   # FAST and OK are not-miss

    def test_drill_cost_fast(self):
        rows = [{"cost_question": "Y", "onset": "1.2"},
                {"cost_question": "Y", "onset": "5.0"},
                {"cost_question": "N", "onset": "0.4"}]
        s = P.drill_series(rows)
        self.assertEqual(s["drill_hit_%"], [100, 100, 0])
        self.assertEqual(s["cost_fast_%"], [100, 0, 0])       # only hit + <=2s


class Trend(unittest.TestCase):
    def test_buckets(self):
        seq = [1, 2, 3, 4, 5, 6, 7, 8]
        self.assertEqual(P.trend(seq, n=4), "improving")
        self.assertEqual(P.trend(list(reversed(seq)), n=4), "declining")
        self.assertEqual(P.trend([3, 3, 3, 3, 3, 3, 3, 3], n=4), "plateau")
        self.assertEqual(P.trend([1, 2], n=4), "not enough data")


class Coach(unittest.TestCase):
    def test_weakness_to_drill(self):
        metrics = {"opener_latency_s": 2.0, "ack_rate_%": 100, "star_solid_%": 50,
                   "criteria/5": 5, "reflex_%": 100, "median_onset_s": 1.0}
        cmds = P.coach(metrics)
        self.assertIn("--paraphrase --beat opener", cmds)
        self.assertIn("--star", cmds)
        self.assertNotIn("--objection", cmds)   # ack + reflex fine

    def test_objection_coached_via_reflex_onset(self):
        cmds = P.coach({"reflex_%": 80, "median_onset_s": 3.0})
        self.assertIn("--objection", cmds)

    def test_sub_five_criteria_coachable(self):
        cmds = P.coach({"criteria/5": 4.5})
        self.assertTrue(any("run a full call" in c for c in cmds))

    def test_zero_is_not_hidden(self):
        # a genuine 0 must trigger its drill (uses .get(key, None), not falsy-or)
        cmds = P.coach({"star_solid_%": 0, "drill_hit_%": 0})
        self.assertIn("--star", cmds)
        self.assertIn("--drill", cmds)

    def test_missing_metrics_not_coached(self):
        self.assertEqual(P.coach({}), [])


class Main(unittest.TestCase):
    def test_main_filters_profile_and_lists_metric(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp)
            _write(s / "objection_history.csv",
                   ["session", "verdict", "reflex", "onset", "profile"],
                   [["s1", "FAST", "Y", "1.0", "levitate"],
                    ["s2", "MISS", "N", "0.5", "boostsecurity"]])
            with mock.patch.object(P, "SESSIONS", s), \
                    mock.patch.object(P, "profiles", type("p", (), {"DEFAULT_PROFILE": "generic_saas"})):
                stdout = __import__("io").StringIO()
                with mock.patch("sys.stdout", stdout):
                    rc = P.main(["--profile", "levitate"])
            self.assertEqual(rc, 0)
            self.assertIn("reflex_%", stdout.getvalue())
            self.assertNotIn("boostsecurity", stdout.getvalue())

    def test_main_empty_data_says_no_data_not_on_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp)
            with mock.patch.object(P, "SESSIONS", s):
                stdout = __import__("io").StringIO()
                with mock.patch("sys.stdout", stdout):
                    rc = P.main(["--profile", "levitate"])
            self.assertEqual(rc, 0)
            self.assertIn("No progress data", stdout.getvalue())
            self.assertNotIn("everything on target", stdout.getvalue())

    def test_main_populates_trend_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp)
            rows = [[str(i), "normal", "5", "YES", "", "", "", "", "",
                     f"{max(0, 1.0 - 0.1*i):.1f}s", "2.0s avg", "100%", "n/a",
                     "2 in 349 words (0.6/100)", "80 words", "0 hit(s)", "none", "100s", "levitate"]
                    for i in range(6)]
            _write(s / "history.csv", ["session", "difficulty", "criteria_passed", "verdict",
                                       "c1", "c2", "c3", "c4", "c5", "opener_latency",
                                       "objection_pause", "ack_rate", "pitch_before_pain",
                                       "filler_rate", "longest_turn", "banned_words", "freezes",
                                       "talk_time", "profile"], rows)
            with mock.patch.object(P, "SESSIONS", s):
                stdout = __import__("io").StringIO()
                with mock.patch("sys.stdout", stdout):
                    P.main(["--profile", "levitate", "--n", "3"])
            out = stdout.getvalue()
            self.assertIn("trend", out)
            self.assertTrue(any(x in out for x in ("improving", "plateau", "declining")))


if __name__ == "__main__":
    unittest.main()
