"""Crash-safe sessions: an aborted call still persists report + audio + history."""
from __future__ import annotations

import random
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mock_call
import profiles

try:
    from test_warmth import WARM_CALL            # discover -s tests / direct run
except ImportError:                              # package-style invocation
    from tests.test_warmth import WARM_CALL


def _args(profile="generic_saas"):
    return types.SimpleNamespace(
        difficulty="normal", profile=profile, text=True, seed=None,
        model="base.en", fast=False, device=None, silence=3.0,
    )


class _Boom:
    """A Stage whose buyer line explodes mid-call."""
    def __init__(self, stage, exc):
        self._stage, self._exc = stage, exc
        self.id, self.expects = stage.id, stage.expects
        self.is_objection, self.objection_label = stage.is_objection, stage.objection_label
    def line(self, landed):
        raise self._exc


class CrashSafeTests(unittest.TestCase):
    def _run(self, tmp, script, lines, eof=False):
        old = mock_call.SESSIONS
        mock_call.SESSIONS = Path(tmp)
        it = iter(lines)

        def fake_input(prompt=""):
            try:
                return next(it)
            except StopIteration:
                if eof:
                    raise EOFError
                return ""

        try:
            with mock.patch("builtins.input", fake_input):
                mock_call.run_call(_args(), script=script)
        finally:
            mock_call.SESSIONS = old

    def test_keyboard_interrupt_saves_partial(self):
        profile = profiles.get_profile("generic_saas")
        stages = profiles.build_script("normal", random.Random(0), profile)
        stages[3] = _Boom(stages[3], KeyboardInterrupt())
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(KeyboardInterrupt):
                self._run(tmp, stages, WARM_CALL)
            md = (Path(tmp) / "generic_saas").rglob("report.md").__next__() \
                .read_text(encoding="utf-8")
            self.assertIn("PARTIAL", md)
            self.assertTrue((Path(tmp) / "history.csv").exists())

    def test_runtime_error_saves_partial(self):
        profile = profiles.get_profile("generic_saas")
        stages = profiles.build_script("normal", random.Random(0), profile)
        stages[3] = _Boom(stages[3], RuntimeError("boom"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self._run(tmp, stages, WARM_CALL)
            reports = list((Path(tmp) / "generic_saas").rglob("report.md"))
            self.assertTrue(reports and "PARTIAL" in reports[0].read_text(encoding="utf-8"))

    def test_eof_in_text_mode_saves_partial(self):
        profile = profiles.get_profile("generic_saas")
        stages = profiles.build_script("normal", random.Random(0), profile)
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, stages, WARM_CALL[:3], eof=True)   # dry pipe -> EOFError
            reports = list((Path(tmp) / "generic_saas").rglob("report.md"))
            self.assertTrue(reports and "PARTIAL" in reports[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
