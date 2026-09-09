"""regrade.py must honour MOCKCALL_SESSIONS like every other module, so a
re-score can never read from or write to the real sessions/ folder.

    .venv/Scripts/python.exe tests/test_regrade.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CliRegrade(unittest.TestCase):
    def _run(self, argv, sessions):
        env = os.environ.copy()
        env["MOCKCALL_SESSIONS"] = str(sessions)
        return subprocess.run(
            [sys.executable, str(ROOT / "regrade.py"), *argv],
            text=True, capture_output=True, cwd=str(ROOT), timeout=60, env=env,
        )

    @staticmethod
    def _seed_session(root: Path) -> None:
        d = root / "2026-08-20_111111"
        d.mkdir(parents=True)
        (d / "session.wav").write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        (d / "report.md").write_text(
            "# Mock Cold Call - Session 2026-08-20_111111\n\n"
            "- **Difficulty:** normal\n"
            "- **Result:** 4/5 criteria at PASS or better\n"
            "- **Verdict:** YES -- reads like a real call.\n"
            "- **Audio:** `session.wav`\n",
            encoding="utf-8",
        )

    def test_reads_from_mockcall_sessions_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_session(root)
            proc = self._run([], root)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("2026-08-20_111111", proc.stdout)

    def test_real_sessions_dir_untouched(self):
        real = ROOT / "sessions"
        before = {p.name for p in real.iterdir()} if real.exists() else set()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_session(root)
            self._run(["--write"], root)
        after = {p.name for p in real.iterdir()} if real.exists() else set()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
