"""Single-file HTML listen-back report.

Writes sessions/<profile>/<ts>/session.html next to report.md: the call audio
embedded as a data URI and a per-turn timeline -- click a turn, hear that
moment. No external assets, works offline straight from disk.
"""
from __future__ import annotations

import base64
from typing import Sequence

import grader

_CSS = """
body{font-family:Consolas,monospace;max-width:900px;margin:2rem auto;padding:0 1rem;
     background:#111;color:#ddd}
h1{font-size:1.2rem} .badge{color:#7C4;border:1px solid #7C4;padding:.1rem .5rem}
audio{width:100%;margin:1rem 0}
.turn{border-left:3px solid #444;padding:.4rem .8rem;margin:.6rem 0}
.turn.buyer{border-color:#C62} .turn time{color:#888;font-size:.8rem}
button{background:#333;color:#ddd;border:1px solid #555;cursor:pointer;
       padding:.15rem .6rem;margin-right:.6rem}
button:hover{background:#555} .meta{color:#888;font-size:.8rem}
"""

_JS = """
const a = document.getElementById('call');
document.querySelectorAll('button.turnbtn').forEach(b => b.onclick = () => {
  a.currentTime = parseFloat(b.dataset.start); a.play(); b.scrollIntoView({block:'center'});
});
"""


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _timing(t: grader.Turn) -> str:
    bits = []
    if t.onset_latency is not None:
        bits.append(f"first word after {t.onset_latency:.1f}s")
    if t.duration:
        bits.append(f"{t.duration:.0f}s")
    if t.internal_gaps:
        bits.append("gaps: " + ", ".join(f"{g:.1f}s" for g in t.internal_gaps))
    return "; ".join(bits)


def render(session_id: str, rep: grader.Report, wav_bytes: bytes) -> str:
    uri = ("data:audio/wav;base64,"
           + base64.b64encode(wav_bytes).decode("ascii"))
    out = [f"""<!doctype html><html><head><meta charset="utf-8">
<title>Mock call {session_id}</title><style>{_CSS}</style></head><body>""",
           f"<h1>MOCK CALL <span class='badge'>{_esc(rep.profile)}</span> "
           f"{_esc(rep.difficulty)} &mdash; {session_id}</h1>",
           f"<p><b>{rep.score_line}.</b> {_esc(rep.verdict)}</p>",
           f"<audio id='call' controls src='{uri}'></audio>",
           "<h2>Timeline</h2>"]
    for t, start in zip(rep.turns, rep.turn_starts):
        who = rep.buyer or "BUYER"
        out.append(
            f"<div class='turn buyer'><time>{start:.1f}s</time> "
            f"<button class='turnbtn' data-start=\"{start:.1f}\">&#9654; from here</button>"
            f"<b>{_esc(who)}:</b> {_esc(t.pm_line)}</div>"
            f"<div class='turn'><time>{start + (t.onset_latency or 0):.1f}s</time> "
            f"<button class='turnbtn' data-start=\"{start:.1f}\">&#9654;</button>"
            f"<b>YOU:</b> {_esc(t.text) or '<i>[silence]</i>'} "
            f"<span class='meta'>{_esc(_timing(t))}</span></div>")
    out.append(f"<script>{_JS}</script></body></html>")
    return "\n".join(out)
