"""RIQ briefs: complete, well-formed, one per playbook persona edition."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import riq_briefs as B


class BriefBankTests(unittest.TestCase):
    def test_twelve_briefs_six_personas(self):
        self.assertEqual(len(B.BRIEFS), 12)
        personas = {b.persona for b in B.BRIEFS}
        self.assertEqual(len(personas), 6)
        for p in personas:
            self.assertEqual(len([b for b in B.BRIEFS if b.persona == p]), 2)

    def test_unique_ids_v1_v2(self):
        ids = [b.id for b in B.BRIEFS]
        self.assertEqual(len(ids), len(set(ids)))
        for b in B.BRIEFS:
            self.assertIn(b.id[-1], "12")          # V1 / V2 suffix

    def test_required_fields_nonempty(self):
        for b in B.BRIEFS:
            for field in ("persona", "title", "company_desc", "external_trigger",
                          "internal_signal", "challenge_hint", "status_quo",
                          "pickup", "play", "source"):
                self.assertTrue(getattr(b, field).strip(), f"{b.id}.{field} empty")
            self.assertTrue(b.pains, f"{b.id}.pains empty")
            self.assertTrue(b.objections, f"{b.id}.objections empty")
            self.assertIn("R", b.riq_terms, f"{b.id} missing R terms")
            self.assertIn("I", b.riq_terms, f"{b.id} missing I terms")

    def test_riq_terms_are_valid_regexes(self):
        for b in B.BRIEFS:
            for kind, pats in b.riq_terms.items():
                self.assertIn(kind, ("R", "I"))
                for p in pats:
                    re.compile(p)                  # raises on bad regex

    def test_get_brief(self):
        a1 = B.get_brief("A1")
        self.assertEqual(a1.persona, "Susie")
        with self.assertRaises(KeyError):
            B.get_brief("Z9")

    def test_brief_ids_listing(self):
        listing = B.list_briefs()
        self.assertIn("A1", listing)
        self.assertIn("F2", listing)


if __name__ == "__main__":
    unittest.main()
