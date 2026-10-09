"""Golden grading corpus: good calls pass, weak calls fail. No audio needed."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))         # sibling: golden
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # root: grader, profiles

import golden


GOOD = ["generic_saas_good.txt"]
WEAK = ["generic_saas_weak.txt"]


class GoldenCorpusTests(unittest.TestCase):
    def test_good_calls_grade_4plus_and_yes(self):
        for name in GOOD:
            with self.subTest(name=name):
                rep = golden.simulate("generic_saas", golden.load_lines(name))
                detail = "; ".join(f"{c.name}={c.level}" for c in rep.criteria)
                self.assertGreaterEqual(rep.passed_count, 4, detail)
                self.assertTrue(rep.verdict.startswith("YES"), rep.verdict)

    def test_weak_calls_grade_2orless_and_no(self):
        for name in WEAK:
            with self.subTest(name=name):
                rep = golden.simulate("generic_saas", golden.load_lines(name))
                detail = "; ".join(f"{c.name}={c.level}" for c in rep.criteria)
                self.assertLessEqual(rep.passed_count, 2, detail)
                self.assertTrue(rep.verdict.startswith("NO"), rep.verdict)


if __name__ == "__main__":
    unittest.main()
