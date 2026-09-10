"""Profile registry: defaults, lookup, and the fields the engine depends on."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import profiles as PF


class Registry(unittest.TestCase):
    def test_generic_saas_is_default(self):
        self.assertEqual(PF.DEFAULT_PROFILE, "generic_saas")

    def test_lookup_known_and_unknown(self):
        self.assertIsInstance(PF.get_profile("generic_saas"), PF.Profile)
        self.assertIsInstance(PF.get_profile("procore"), PF.Profile)
        with self.assertRaises(KeyError):
            PF.get_profile("nope")

    def test_list_profiles_contains_both(self):
        self.assertIn("generic_saas", PF.list_profiles())
        self.assertIn("procore", PF.list_profiles())


class Shape(unittest.TestCase):
    def test_generic_has_required_fields(self):
        p = PF.get_profile("generic_saas")
        for field in ("high_value_terms", "whisper_primer", "objection_pools",
                      "pain_drill_cues", "beat_order", "buyer_name", "objective"):
            self.assertTrue(getattr(p, field), field)

    def test_build_script_returns_stages(self):
        import random
        p = PF.get_profile("generic_saas")
        stages = p.build_script("normal", random.Random(0), p)
        self.assertEqual(len(stages), 9)
        self.assertTrue(all(s.id for s in stages))


if __name__ == "__main__":
    unittest.main()
