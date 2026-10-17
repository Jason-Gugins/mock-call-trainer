"""OpenRouter client: transport-injected (no network in tests), retries, auth."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openrouter_client as OR


class _FakeTransport:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, path, payload):
        self.calls.append((path, payload))
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class ChatTests(unittest.TestCase):
    def test_success_returns_content(self):
        t = _FakeTransport([{"choices": [{"message": {"content": "Go ahead."}}]}])
        out = OR.chat([{"role": "user", "content": "hi"}], transport=t)
        self.assertEqual(out, "Go ahead.")
        path, payload = t.calls[0]
        self.assertEqual(path, "/chat/completions")
        self.assertEqual(payload["messages"][0]["content"], "hi")

    def test_key_validated_even_with_injected_transport(self):
        t = _FakeTransport([])
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OR.OpenRouterError) as ctx:
                OR.chat([{"role": "user", "content": "hi"}], transport=t)
        self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))
        self.assertEqual(t.calls, [])            # nothing was sent

    def test_auth_recorded_when_key_present(self):
        t = _FakeTransport([{"choices": [{"message": {"content": "ok"}}]}])
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            OR.chat([{"role": "user", "content": "hi"}], transport=t)
        self.assertTrue(OR._last_auth.startswith("Bearer sk-test"))

    def test_retries_then_succeeds(self):
        t = _FakeTransport([TimeoutError("t1"), TimeoutError("t2"),
                            {"choices": [{"message": {"content": "ok"}}]}])
        with mock.patch.object(OR, "_sleep", lambda s: None):
            out = OR.chat([{"role": "user", "content": "hi"}], transport=t)
        self.assertEqual(out, "ok")
        self.assertEqual(len(t.calls), 3)

    def test_exhausted_retries_raises(self):
        t = _FakeTransport([TimeoutError("x")] * 3)
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with mock.patch.object(OR, "_sleep", lambda s: None):
                with self.assertRaises(OR.OpenRouterError):
                    OR.chat([{"role": "user", "content": "hi"}], transport=t)


class TtsTests(unittest.TestCase):
    def test_tts_requests_mp3_and_returns_bytes(self):
        t = _FakeTransport([b"ID3" + b"\x00" * 300])
        out = OR.tts("hello", transport=t)
        self.assertEqual(len(out), 303)
        path, payload = t.calls[0]
        self.assertEqual(path, "/audio/speech")
        self.assertEqual(payload["response_format"], "mp3")

    def test_tts_rejects_tiny_payloads(self):
        t = _FakeTransport([b"RIFF...."])        # 8 bytes: error page, not audio
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with self.assertRaises(OR.OpenRouterError):
                OR.tts("hello", transport=t)


class ModelListTests(unittest.TestCase):
    def test_list_models_parses_ids(self):
        t = _FakeTransport([{"data": [{"id": "a/b"}, {"id": "c/d"}]}])
        self.assertEqual(OR.list_models(transport=t), ["a/b", "c/d"])

    def test_tts_models_use_speech_filter(self):
        t = _FakeTransport([{"data": [{"id": "deepgram/flux-tts"}]}])
        self.assertEqual(OR.list_tts_models(transport=t),
                         ["deepgram/flux-tts"])
        self.assertEqual(t.calls[0][0], "/models?output_modalities=speech")


if __name__ == "__main__":
    unittest.main()


class ZaiChatTests(unittest.TestCase):
    """chat_zai: Z.ai Coding Plan buyer brain (separate platform from OpenRouter)."""

    def test_success_payload_and_content(self):
        t = _FakeTransport([{"choices": [{"message": {"content": "Go."}}]}])
        with mock.patch.dict(os.environ, {"ZAI_API_KEY": "zai-key"}):
            out = OR.chat_zai([{"role": "user", "content": "hi"}], transport=t)
        self.assertEqual(out, "Go.")
        path, payload = t.calls[0]
        self.assertEqual(path, "/chat/completions")
        self.assertEqual(payload["model"], "glm-5.3-flash")
        # GLM emits reasoning_content before content: thinking must be OFF or a
        # small max_tokens budget dies inside hidden reasoning (live-verified).
        self.assertEqual(payload["thinking"], {"type": "disabled"})

    def test_missing_key_is_actionable(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OR.OpenRouterError) as ctx:
                OR.chat_zai([{"role": "user", "content": "hi"}],
                            transport=_FakeTransport([]))
        self.assertIn("ZAI_API_KEY", str(ctx.exception))
