"""Progress aggregation and coaching. Uses trend's value parsers."""
from __future__ import annotations
import csv, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import progress as P


def _write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

class Aggregate(unittest.TestCase):
    def test_full_metrics(self):
        rows = [{"criteria_passed": "4", "opener_latency": "1.7s", "ack_rate": "66%",
                 "filler_rate": "2 in 349 words (0.6/100)", "longest_turn": "84 words",
                 "banned_words": "0 hit(s)"},
                {"criteria_passed": "5", "opener_latency": "0.2s", "ack_rate": "100%",
                 "filler_rate": "7 in 480 words (1.5/100)", "longest_turn": "92 words",
                 "banned_words": "1 hit(s)"}]
        m = P.aggregate_full(rows)
        self.assertEqual(m["criteria/5"], (4 + 5) / 2)
        self.assertEqual(m["opener_latency_s"], (1.7 + 0.2) / 2)
        self.assertEqual(m["ack_rate_%"], 83)
        self.assertEqual(m["filler_rate_per100"], (0.6 + 1.5) / 2)

    def test_objection_rate_and_onset(self):
        rows = [{"verdict": "FAST", "reflex": "Y", "onset": "1.0"},
                {"verdict": "MISS", "reflex": "Y", "onset": "0.5"},
                {"verdict": "OK", "reflex": "N", "onset": "3.0"}]
        m = P.aggregate_objection(rows)
        self.assertAlmostEqual(m["reflex_%"], 2 / 3 * 100, places=6)
        self.assertAlmostEqual(m["median_onset_s"], 1.0, places=1)   # median of hits

    def test_trend_buckets(self):
        seq = [1, 2, 3, 4, 5, 6, 7, 8]          # clearly improving
        self.assertEqual(P.trend(seq, n=4), "improving")
        self.assertEqual(P.trend(list(reversed(seq)), n=4), "declining")
        self.assertEqual(P.trend([3, 3, 3, 3, 3, 3, 3, 3], n=4), "plateau")

class Coach(unittest.TestCase):
    def test_weakness_to_drill(self):
        metrics = {"opener_latency_s": 2.0, "ack_rate_%": 100, "star_solid_%": 50,
                   "criteria/5": 5}
        cmds = P.coach(metrics)
        self.assertIn("--paraphrase --beat opener", cmds)
        self.assertIn("--star", cmds)
        self.assertNotIn("--objection", cmds)   # ack fine

    def test_main_filters_by_profile(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp)
            _write(s / "objection_history.csv", ["session","verdict","reflex","onset","profile"],
                   [["s1","FAST","Y","1.0","levitate"], ["s2","MISS","N","0.5","boostsecurity"]])
            # patch SESSIONS and re-run main
            with mock.patch.object(P, "SESSIONS", s):
                rows = P._profile_rows(s / "objection_history.csv", "levitate")
            self.assertEqual(len(rows), 1)

if __name__ == "__main__":
    unittest.main()
