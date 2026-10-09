"""Call HUD line: pure formatting, wired into run_call in the next task."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mock_call
import profiles


class HudTests(unittest.TestCase):
    def test_plain_turn(self):
        line = mock_call.hud_line(3, 9, "react_handle_1", questions=2,
                                  objections_handled=1, warmth=62)
        self.assertIn("turn 3/9", line)
        self.assertIn("questions 2", line)
        self.assertIn("objections handled 1", line)   # shows on every turn: it's the ledger
        self.assertIn("warmth 62%", line)

    def test_counts_format(self):
        line = mock_call.hud_line(1, 9, "pickup", questions=0,
                                  objections_handled=0, warmth=50)
        self.assertIn("questions 0", line)


if __name__ == "__main__":
    unittest.main()
