"""Minimal OpenRouter client (stdlib urllib only — no new pip dependencies).

Transport is injectable for tests: transport(path, payload_dict) -> dict|bytes.
A real transport hits https://openrouter.ai/api/v1<path> with JSON bodies.
Key handling: OPENROUTER_API_KEY from the environment or a repo-root .env
(loaded once at import; .env is gitignored). Key presence is validated in
_request BEFORE any transport runs, so misconfiguration is never retried.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

BASE = "https://openrouter.ai/api/v1"
_APP_HEADERS = {"HTTP-Referer": "https://github.com/Jason-Gugins/mock-call-trainer",
                "X-OpenRouter-Title": "mock-call-trainer"}

_last_auth = ""     # captured for tests; never logs the key itself


class OpenRouterError(Exception):
    pass


def _load_dotenv(path: Optional[Path] = None) -> None:
    """Tiny stdlib .env loader (KEY=VALUE lines); real env always wins."""
    p = path or (Path(__file__).resolve().parent / ".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


_load_dotenv()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _api_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def _default_transport(path: str, payload: Dict, timeout: float = 60.0,
                       method: str = "POST"):
    global _last_auth
    _last_auth = f"Bearer {_api_key()}"
    headers = {"Authorization": _last_auth, "Content-Type": "application/json",
               **_APP_HEADERS}
    data = json.dumps(payload).encode() if method == "POST" else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise OpenRouterError(f"OpenRouter {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise OpenRouterError(f"OpenRouter unreachable: {e}") from e


def _request(path, payload, transport=None, retries=2, parse_json=True,
             timeout=60.0, method: str = "POST"):
    if not _api_key():
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set. export OPENROUTER_API_KEY=<key> "
            "(or put it in .env next to mock_call.py).")
    global _last_auth
    _last_auth = f"Bearer {_api_key()}"
    send = transport or _default_transport
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            raw = send(path, payload) if transport is not None \
                else send(path, payload, timeout=timeout, method=method)
            # injected transports may hand back already-parsed JSON; only
            # decode raw payloads (the default urllib transport returns bytes)
            if parse_json and isinstance(raw, (bytes, bytearray, str)):
                return json.loads(raw)
            return raw
        except OpenRouterError:
            raise                          # config errors: don't retry
        except Exception as e:             # noqa: BLE001  transient -> backoff
            last = e
            if attempt < retries:
                _sleep(0.8 * (attempt + 1))
    raise OpenRouterError(f"OpenRouter call failed after {retries + 1} "
                          f"attempts: {last}")


def resolved_chat_model(model: Optional[str] = None) -> str:
    """The chat model a call will actually use (for logs/history accuracy)."""
    return model or os.environ.get("OPENROUTER_MODEL") or "z-ai/glm-5.3-flash"


ZAI_BASE = "https://api.z.ai/api/coding/paas/v4"
ZAI_DEFAULT_MODEL = os.environ.get("ZAI_MODEL") or "glm-5.3-flash"


def chat_zai(messages: List[Dict], model: Optional[str] = None, transport=None,
             max_tokens: int = 120, temperature: float = 0.8) -> str:
    """Buyer brain via the Z.ai Coding Plan (ZAI_API_KEY, endpoint
    api.z.ai/api/coding/paas/v4) — runs on the subscription instead of
    OpenRouter credits. GLM emits reasoning_content BEFORE content, so the
    thinking switch must be off: with it on, a small max_tokens budget dies
    inside hidden reasoning and content comes back empty (live-verified).
    Raises OpenRouterError on any failure, so llm_call's fallback net is
    provider-agnostic."""
    payload = {"model": model or ZAI_DEFAULT_MODEL,
               "messages": messages, "max_tokens": max_tokens,
               "temperature": temperature,
               "thinking": {"type": "disabled"}}
    global _last_auth
    key = os.environ.get("ZAI_API_KEY", "").strip()
    if not key:
        raise OpenRouterError(
            "ZAI_API_KEY is not set. export ZAI_API_KEY=<key> (or put it in "
            ".env next to mock_call.py), or use --buyer-provider openrouter.")
    _last_auth = f"Bearer {key}"
    headers = {"Authorization": _last_auth, "Content-Type": "application/json"}
    last: Optional[Exception] = None
    for attempt in range(3):
        try:
            if transport is not None:
                raw = transport("/chat/completions", payload)
            else:
                req = urllib.request.Request(
                    ZAI_BASE + "/chat/completions",
                    data=json.dumps(payload).encode(), headers=headers,
                    method="POST")
                with urllib.request.urlopen(req, timeout=90) as r:
                    raw = r.read()
            data = json.loads(raw) if isinstance(raw, (bytes, bytearray, str)) \
                else raw
            return data["choices"][0]["message"]["content"].strip()
        except OpenRouterError:
            raise
        except Exception as e:                     # noqa: BLE001  transient
            last = e
            if attempt < 2:
                _sleep(0.8 * (attempt + 1))
    raise OpenRouterError(f"Z.ai chat failed after 3 attempts: {last}")


def chat(messages: List[Dict], model: Optional[str] = None, transport=None,
         max_tokens: int = 120, temperature: float = 0.8) -> str:
    payload = {"model": resolved_chat_model(model),
               "messages": messages, "max_tokens": max_tokens,
               "temperature": temperature,
               # a reasoning-mode reply can burn a 120-token budget on hidden
               # reasoning and come back empty; the buyer must answer fast
               "reasoning": {"exclude": True, "effort": "minimal"}}
    data = _request("/chat/completions", payload, transport=transport)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise OpenRouterError(f"unexpected chat response shape") from e


def tts(text: str, transport=None, voice: Optional[str] = "flux-bree-en") -> bytes:
    """Buyer speech via OpenRouter TTS. mp3 explicitly: the default format is
    headerless pcm, which soundfile cannot parse from memory. Raises
    OpenRouterError when unavailable — callers fall back to SAPI Voice."""
    payload = {"model": os.environ.get("OPENROUTER_TTS_MODEL")
               or "deepgram/flux-tts",
               "input": text, "response_format": "mp3"}
    if voice:
        payload["voice"] = voice
    raw = _request("/audio/speech", payload, transport=transport, parse_json=False)
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 100:
        raise OpenRouterError("TTS returned no usable audio")
    return bytes(raw)


def list_models(transport=None) -> List[str]:
    data = _request("/models", {}, transport=transport, method="GET")
    return [m["id"] for m in data.get("data", [])]


def list_tts_models(transport=None) -> List[str]:
    """TTS models appear ONLY under the speech output-modality filter."""
    data = _request("/models?output_modalities=speech", {},
                    transport=transport, method="GET")
    return [m["id"] for m in data.get("data", [])]
