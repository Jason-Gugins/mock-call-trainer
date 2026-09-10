"""regrade.py must honour MOCKCALL_SESSIONS like every other module, so a
re-score can never read from or write to the real sessions/ folder.

    .venv/Scripts/python.exe tests/test_regrade.py
"""
from __future__ import annotations

import hashlib
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

    @staticmethod
    def _seed_drill_dir(root: Path, name: str = "2026-08-20_222222-drill") -> None:
        d = root / name
        d.mkdir(parents=True)
        (d / "session.wav").write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        (d / "report.md").write_text(
            f"# Pain-reveal drill - {name}\n\n"
            "| Shot | Verdict | Onset | You said |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | **FAST** | 2.0s | Who ate that? |\n",
            encoding="utf-8",
        )

    def test_reads_from_mockcall_sessions_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_session(root)
            proc = self._run([], root)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("2026-08-20_111111", proc.stdout)

    def test_drill_sessions_excluded_from_history_rebuild(self):
        # regrade --write rebuilds history.csv; a *-drill folder must NOT be
        # folded in as a junk 0/5 row (the live app keeps drill history apart).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_session(root)
            self._seed_drill_dir(root)
            proc = self._run(["--write"], root)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            hist = root / "history.csv"
            self.assertTrue(hist.exists())
            content = hist.read_text(encoding="utf-8")
            self.assertIn("2026-08-20_111111", content)
            self.assertNotIn("2026-08-20_222222-drill", content)

    def test_reads_sessions_nested_under_profile_dir(self):
        # New layout: sessions/<profile>/<ts>/. regrade must find those too.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prof_dir = root / "generic_saas"
            prof_dir.mkdir(parents=True)
            d = prof_dir / "2026-08-21_111111"
            d.mkdir()
            (d / "session.wav").write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
            (d / "report.md").write_text(
                "# Mock Cold Call [generic_saas] - Session 2026-08-21_111111\n\n"
                "- **Difficulty:** normal\n"
                "- **Result:** 4/5 criteria at PASS or better\n"
                "- **Verdict:** YES -- reads like a real call.\n"
                "- **Audio:** `session.wav`\n", encoding="utf-8")
            proc = self._run([], root)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("2026-08-21_111111", proc.stdout)

    def test_real_sessions_dir_untouched(self):
        # Snapshot FULL content digests of the real sessions dir, not just file
        # names: a --write that rewrites history.csv or report.md in place would
        # keep every name identical while mutating the data, and a name-set
        # comparison would miss it.
        real = ROOT / "sessions"

        def snap(d):
            if not d.exists():
                return {}
            return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in d.rglob("*") if p.is_file()}

        before = snap(real)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_session(root)
            self._run(["--write"], root)
        self.assertEqual(before, snap(real))
        self.assertTrue((real / "history.csv").is_file())


if __name__ == "__main__":
    unittest.main()
