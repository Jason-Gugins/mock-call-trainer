"""Progress aggregation, trend, coaching, and the report CLI. Uses trend's parsers."""
from __future__ import annotations
import csv, sys, tempfile, unittest, unittest.mock as mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import progress as P
import trend as T


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


class Llm(unittest.TestCase):
    """The LLM funnel: sessions/llm_history.csv (global - it has no profile column)."""

    def test_llm_series_mapping(self):
        rows = [{"criteria_passed": "4", "riq_hook": "STRONG", "riq_challenge": "PASS",
                 "riq_cta": "FAIL", "fallback": "N"},
                {"criteria_passed": "5", "riq_hook": "PASS", "riq_challenge": "STRONG",
                 "riq_cta": "PASS", "fallback": "Y"},
                {"criteria_passed": "0", "riq_hook": "FAIL", "riq_challenge": "",
                 "riq_cta": "", "fallback": "N"}]
        s = P.llm_series(rows)
        self.assertEqual(s["riq_pass_%"], [80.0, 100.0, 0.0])        # criteria/5*100
        self.assertEqual(s["hook_%"], [100.0, 50.0, 0.0])            # STRONG/PASS/FAIL
        self.assertEqual(s["challenge_%"], [50.0, 100.0, 0.0])       # blank -> 0.0
        self.assertEqual(s["cta_%"], [0.0, 50.0, 0.0])               # missing key -> 0.0
        self.assertEqual(s["fallback_free_%"], [100.0, 0.0, 100.0])  # N=free, Y=fallback

    def test_sources_lists_llm_last(self):
        self.assertEqual(P.SOURCES[-1], ("llm", "llm_history.csv", P.llm_series))

    def test_collect_reads_llm_rows_despite_profile_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp)
            _write(s / "llm_history.csv",
                   ["session", "brief", "criteria_passed", "riq_hook",
                    "riq_challenge", "riq_cta", "fallback"],
                   [["s1", "C1", "4", "STRONG", "PASS", "FAIL", "N"],
                    ["s2", "B2", "5", "STRONG", "STRONG", "STRONG", "N"]])
            with mock.patch.object(P, "SESSIONS", s):
                series, notes = P.collect("levitate")
        self.assertEqual(series["riq_pass_%"], [80.0, 100.0])   # no profile column -> kept
        self.assertEqual(series["hook_%"], [100.0, 100.0])
        self.assertNotIn("llm: no rows yet", notes)

    def test_llm_by_brief_groups_and_finds_weakest(self):
        rows = [
            {"brief": "C1", "criteria_passed": "2", "riq_hook": "FAIL",
             "riq_challenge": "STRONG", "riq_cta": "PASS", "difficulty": "normal"},
            {"brief": "C1", "criteria_passed": "4", "riq_hook": "PASS",
             "riq_challenge": "STRONG", "riq_cta": "STRONG", "difficulty": "hostile"},
            {"brief": "B2", "criteria_passed": "5", "riq_hook": "STRONG",
             "riq_challenge": "STRONG", "riq_cta": "STRONG", "difficulty": "normal"},
        ]
        d = P.llm_by_brief(rows)
        self.assertEqual(set(d), {"C1", "B2"})
        self.assertEqual(d["C1"]["reps"], 2)
        self.assertAlmostEqual(d["C1"]["mean_pass"], 3.0)
        self.assertEqual(d["C1"]["weakest"], "riq_hook")   # mean 25 vs 100 vs 75
        self.assertEqual(d["C1"]["mix"], "1N/1H")
        self.assertEqual(d["B2"]["mean_pass"], 5.0)

    def test_coach_grid_on_weak_hook(self):
        self.assertIn("--grid  # build the R+I+Q cold", P.coach({"hook_%": 50.0}))

    def test_coach_llm_reflex_and_close(self):
        cmds = P.coach({"challenge_%": 50.0, "cta_%": 0.0})
        self.assertIn("--objection --llm  # reflexes", cmds)
        self.assertIn("--llm --brief <weakest>  # close with two times", cmds)


class LlmView(unittest.TestCase):
    """--llm: per-brief breakdown of the LLM funnel instead of the standard view."""

    def test_main_llm_prints_per_brief_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp)
            _write(s / "llm_history.csv",
                   ["session", "difficulty", "brief", "criteria_passed", "riq_hook",
                    "riq_challenge", "riq_cta", "fallback"],
                   [["s1", "normal", "C1", "2", "FAIL", "STRONG", "PASS", "N"],
                    ["s2", "hostile", "C1", "4", "PASS", "STRONG", "STRONG", "N"],
                    ["s3", "normal", "B2", "5", "STRONG", "STRONG", "STRONG", "N"]])
            with mock.patch.object(P, "SESSIONS", s):
                stdout = __import__("io").StringIO()
                with mock.patch("sys.stdout", stdout):
                    rc = P.main(["--llm"])
            self.assertEqual(rc, 0)
            out = stdout.getvalue()
            self.assertIn("C1", out)
            self.assertIn("B2", out)
            self.assertIn("riq_hook", out)     # most-failed criterion, by name
            self.assertIn("1N/1H", out)        # difficulty mix for C1
            self.assertIn("3.0", out)          # C1 mean criteria (2+4)/2

    def test_main_llm_no_rows_message_nothing_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp)
            with mock.patch.object(P, "SESSIONS", s):
                stdout = __import__("io").StringIO()
                with mock.patch("sys.stdout", stdout):
                    rc = P.main(["--llm", "--write"])
            self.assertEqual(rc, 0)
            self.assertIn("No LLM funnel data", stdout.getvalue())
            self.assertEqual(list(Path(tmp).rglob("*.md")), [])   # --write suppressed


class TrendRiq(unittest.TestCase):
    """trend.py gains a 'riq' headline column fed by llm_history.csv."""

    def test_llm_riq_reads_sessions_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp)
            _write(s / "llm_history.csv", ["session", "criteria_passed"],
                   [["s1", "4"], ["s2", ""], ["", "5"]])
            with mock.patch.object(T, "SESSIONS", s):
                self.assertEqual(T.llm_riq(), {"s1": 4.0})

    def test_riq_column_aligned_by_session_and_llm_only_appended(self):
        rows = [{"session": "s1", "criteria_passed": "4"},
                {"session": "s2", "criteria_passed": "5"}]
        out = T.tabulate(rows, llm={"s1": 4, "s9": 3})
        lines = out.splitlines()
        self.assertEqual(lines[0].split()[-1], "riq")                 # new last column
        s1 = next(l for l in lines if l.startswith("s1"))
        self.assertTrue(s1.rstrip().endswith("4"))                    # aligned by session id
        s9 = next(l for l in lines if l.startswith("s9"))
        self.assertEqual(s9.split()[0], "s9")                         # appended, not merged
        self.assertEqual(s9.split().count("-"), len(T.HEADLINE) - 1)  # dashes offline
        self.assertEqual(s9.split()[-1], "3")                         # riq score shown

    def test_no_llm_data_leaves_dashes_and_keeps_table(self):
        rows = [{"session": "s1", "profile": "levitate", "criteria_passed": "4"}]
        out = T.tabulate(rows)
        lines = out.splitlines()
        self.assertIn("riq", lines[0])
        s1 = next(l for l in lines if l.startswith("s1/levitate"))
        self.assertEqual(s1.split()[-1], "-")


if __name__ == "__main__":
    unittest.main()
