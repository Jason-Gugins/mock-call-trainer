"""Tiny stdlib .env loader shared by mock_call.py and openrouter_client.py.

KEY=VALUE lines, '#' comments, quotes stripped; real environment variables
always win (setdefault). No dependencies.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent


def load(path: Optional[Path] = None) -> None:
    p = path or (ROOT / ".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))
