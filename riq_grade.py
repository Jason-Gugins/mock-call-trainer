"""Deterministic RIQ scoring for LLM sessions.

The LLM plays the buyer; scoring never does. Five criteria, all measurable:
  riq_opener     permissive interruption (reuses the generic_saas opener Beat
                 concepts: admits cold call + asks time + escape hatch)
  riq_hook       mentioned THIS brief's R and I (brief-scoped regex banks)
  riq_challenge  asked a cost/consequence question (grader.has_implication_question)
  riq_cta        STRONG = two specific times; PASS = low-friction ask (one-page
                 / interest ask) or a confirmed callback time; FAIL = neither.
                 (The playbook's CTA-variants doctrine: rigid ask on a warm yes,
                 low-friction ask on a busy maybe; a booked callback is a booked
                 meeting.)
  riq_listen     2+ discovery questions total and no banned-SaaS words
The report adapts to ONE framework — RIQ — and the same definitions drive both
sides of the trainer: riq_prompts teaches the buyer the framework, riq_grade
scores the candidate on it. A future framework swap means touching exactly
those two modules; nothing else in the codebase knows methodology exists.
Leaks reuse the wave-1 primitives (filler rate, banned words, freezes, talk
time, opener latency). History goes to llm_history.csv — history.csv is never
touched. render_console/render_markdown mirror the wave-1 style and MUST
include: the brief card, the five-criteria table, the leaks table, the verdict,
the coach lines, and the token "RIQ" in the title (tests pin this), plus
"FALLBACK" when rep.fallback is set.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import grader
import profiles
import riq_briefs

LLM_HISTORY_FIELDS = [
    "session", "difficulty", "brief", "model", "criteria_passed", "verdict",
    "riq_opener", "riq_hook", "riq_challenge", "riq_cta", "riq_listen",
    "opener_latency", "filler_rate", "banned_words", "freezes", "talk_time",
    "turns", "fallback",
]

STRONG, PASS, FAIL = "STRONG", "PASS", "FAIL"

# Low-friction CTA: one-pager / interest ask (AV playbook CTA variants doctrine).
LOW_FRICTION_RE = (r"\bsend (you|me) (the |a )?(one|2|two)[- ]pager?\b"
                   r"|\bone-?page (breakdown|rundown|overview)\b"
                   r"|\bif it resonates\b|\bwant me to send\b")
CALLBACK_RE = (r"\bi'?ll call (you )?(right )?(back|after)\b"
               r"|\bcall (me|you) (back|after|when)\b")


@dataclass
class RiqCriterion:
    key: str
    name: str
    level: str
    detail: str
    evidence: str = ""


@dataclass
class RiqReport:
    criteria: List[RiqCriterion]
    leaks: List[grader.Leak]
    verdict: str
    passed_count: int
    coach_first: List[str]
    turns: List[grader.Turn]
    difficulty: str = "normal"
    brief_id: str = ""
    persona: str = ""
    buyer: str = ""              # listenback compat (== persona)
    profile: str = "llm"         # listenback compat
    turn_starts: List[float] = field(default_factory=list)   # segment offsets (s)
    model: str = ""
    fallback: bool = False

    @property
    def score_line(self) -> str:
        return f"{self.passed_count}/5 RIQ criteria at PASS or better"


def _opened_permissively(text: str):
    beat = profiles.get_profile("generic_saas").beats["opener"]
    return beat.check_idea(text)


def _cta_level(offers: List[str], all_text: str):
    if len(offers) >= 2:
        return STRONG, ", ".join(offers)
    if re.search(LOW_FRICTION_RE, all_text.lower()):
        return PASS, "low-friction ask (one-page send / interest ask)"
    if re.search(CALLBACK_RE, all_text.lower()):
        return PASS, "confirmed callback time"
    return FAIL, "no specific times and no low-friction ask"


def riq_time_offers(text: str) -> List[str]:
    """Specific time offers, RIQ-broad: day + clock (grader.find_time_offers's
    detection) OR day + a time-of-day word — "Thursday or Friday morning", the
    REAL debrief call's ask, must count. Deduped, order kept."""
    low = grader._norm(text)
    found: List[str] = []
    for m in re.finditer(grader.DAY_RE, low):
        tail = low[m.start(): m.start() + 40][len(m.group(0)):]
        if re.search(grader.CLOCK_RE, tail) or \
                re.search(r"\b(morning|afternoon|evening|tonight|lunch)\b", tail):
            label = m.group(0).strip()
            if label not in found:
                found.append(label)
    return found


def grade_riq(turns: List[grader.Turn], brief, difficulty: str = "normal",
              model: str = "", fallback: bool = False) -> RiqReport:
    all_text = " ".join(t.text for t in turns)
    opener_text = turns[0].text if turns else ""

    ok, missing = _opened_permissively(opener_text)
    c_opener = RiqCriterion("riq_opener", "Permissive-interruption opener",
                            STRONG if ok else FAIL,
                            "admits the cold call + asks for time + gives an out"
                            + ("" if ok else f" — missing: {'; '.join(missing)}"))

    def _hit(kind: str) -> bool:
        return any(re.search(p, all_text.lower())
                   for p in brief.riq_terms.get(kind, []))

    r_hit, i_hit = _hit("R"), _hit("I")
    if r_hit and i_hit:
        hook_level, hook_ev = STRONG, "R and I both present in your words"
    elif r_hit or i_hit:
        hook_level, hook_ev = PASS, ("R present, I not detected" if r_hit
                                     else "I present, R not detected")
    else:
        hook_level, hook_ev = FAIL, "neither the R nor the I came through"
    c_hook = RiqCriterion("riq_hook", "Hook landed (R + I)", hook_level,
                          "named THIS brief's R and I in your words", hook_ev)

    qcount = sum(grader.count_discovery_questions(t.text) for t in turns)
    # RIQ challenge shape ("how are you currently handling X without risking Y")
    # plus the wave-1 implication bank; the real debrief call uses this phrasing.
    CHALLENGE_RE = (r"\bhow (are|do|did) you (currently |actually )?"
                    r"(handling|getting|keeping|tracking|telling|vetting|planning"
                    r"|deploying|marketing)\b")
    impl = any(grader.has_implication_question(t.text)
               or re.search(CHALLENGE_RE, t.text.lower()) for t in turns)
    c_challenge = RiqCriterion(
        "riq_challenge", "Challenge question (cost/status quo)",
        STRONG if impl else FAIL,
        "a consequence question about their process"
        + ("" if impl else " — you never made the status quo cost anything"))

    offers = riq_time_offers(all_text)
    cta_level, cta_ev = _cta_level(offers, all_text)
    c_cta = RiqCriterion("riq_cta", "CTA (two times > low-friction ask)",
                         cta_level, cta_ev or "nothing offered")

    banned = grader.find_matches(all_text, grader.BANNED_PHRASES)
    listen_ok = qcount >= 2 and not banned
    c_listen = RiqCriterion("riq_listen", "Listened (2+ questions, zero SaaS filler)",
                            STRONG if listen_ok else FAIL,
                            f"{qcount} discovery questions"
                            + (f"; banned: {', '.join(banned)}" if banned else ""))

    criteria = [c_opener, c_hook, c_challenge, c_cta, c_listen]
    passed = sum(1 for c in criteria if c.level in (PASS, STRONG))

    leaks: List[grader.Leak] = []
    if turns and turns[0].onset_latency is not None:
        lat = turns[0].onset_latency
        leaks.append(grader.Leak("opener_latency", "Time to first word", f"{lat:.1f}s",
                                 "GOOD" if lat <= 1.5 else "WATCH"))
    total_words = sum(t.words for t in turns) or 1
    filler_total = sum(len(re.findall(p, grader._norm(all_text)))
                       for p in grader.FILLER_PHRASES.values())
    rate = filler_total / total_words * 100
    leaks.append(grader.Leak("filler_rate", "Filler rate",
                             f"{filler_total} ({rate:.1f}/100)",
                             "GOOD" if rate < 3 else "WATCH"))
    leaks.append(grader.Leak("banned_words", "Banned SaaS filler",
                             f"{len(banned)}", "GOOD" if not banned else "LEAK"))
    freezes = [t.index for t in turns if t.froze]
    leaks.append(grader.Leak("freezes", "Dead-air freezes",
                             ", ".join(map(str, freezes)) or "none",
                             "LEAK" if freezes else "GOOD"))
    leaks.append(grader.Leak("talk_time", "Talk time",
                             f"{sum(t.duration for t in turns):.0f}s", "info"))

    hard = any(c.key in ("riq_challenge", "riq_cta") and c.level == FAIL
               for c in criteria)
    if passed >= 4 and not hard:
        verdict = "YES -- RIQ executed; this reads like a real bookable call."
    elif passed >= 3:
        verdict = "NOT YET -- the shape is there; the ask or the challenge slipped."
    else:
        verdict = "NO -- the call never challenged the status quo."

    coach = [f"{c.name}: {c.detail}" for c in criteria if c.level == FAIL]
    for lk in leaks:
        if lk.verdict.startswith("LEAK"):
            coach.append(f"{lk.label} ({lk.value})")
    if not coach:
        coach.append("Clean call. Push every criterion to STRONG on the next rep.")

    return RiqReport(criteria, leaks, verdict, passed, coach[:3], turns,
                     difficulty=difficulty, brief_id=brief.id,
                     persona=brief.persona, buyer=brief.persona, profile="llm",
                     model=model, fallback=fallback)


def append_llm_history(csv_path: Path, session_id: str, rep: RiqReport,
                       brief_id: str, model: str, difficulty: str) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    row = {f: "" for f in LLM_HISTORY_FIELDS}
    row.update({
        "session": session_id, "difficulty": difficulty, "brief": brief_id,
        "model": model, "criteria_passed": rep.passed_count,
        "verdict": rep.verdict.split("--")[0].strip(),
        "opener_latency": next((lk.value for lk in rep.leaks
                                if lk.key == "opener_latency"), ""),
        "filler_rate": next((lk.value for lk in rep.leaks
                             if lk.key == "filler_rate"), ""),
        "banned_words": next((lk.value for lk in rep.leaks
                              if lk.key == "banned_words"), ""),
        "freezes": next((lk.value for lk in rep.leaks if lk.key == "freezes"), ""),
        "talk_time": next((lk.value for lk in rep.leaks
                           if lk.key == "talk_time"), ""),
        "turns": len(rep.turns), "fallback": "Y" if rep.fallback else "N",
    })
    for c in rep.criteria:
        if c.key in row:
            row[c.key] = c.level
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LLM_HISTORY_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


# --------------------------------------------------------------------------
# Renderers (wave-1 style; see the module docstring for the pinned contract)
# --------------------------------------------------------------------------

def _brief_card(rep: RiqReport) -> str:
    """The brief the candidate dialed against — same shape as the dial-time
    persona card, rebuilt from the brief bank (RiqReport carries brief_id)."""
    try:
        b = riq_briefs.get_brief(rep.brief_id)
    except KeyError:
        return f"BRIEF {rep.brief_id}: {rep.persona}"
    return (f"BRIEF {b.label}\n"
            f"  R (external trigger): {b.external_trigger}\n"
            f"  I (internal signal):  {b.internal_signal}\n"
            f"  Q skeleton: {b.challenge_hint}\n"
            f"  CTA: two specific times — or the low-friction one-page ask on a "
            f"busy maybe.\n"
            f"  Play: {b.play}\n"
            f"  Their world: {b.company_desc}\n"
            f"  Source: {b.source}")


def render_console(rep: RiqReport) -> str:
    L = []
    L.append("=" * 72)
    L.append(f"  RIQ SCORECARD  --  brief: {rep.brief_id}  "
             f"difficulty: {rep.difficulty}")
    L.append("=" * 72)
    L.append("")
    if rep.fallback:
        L.append("  FALLBACK -- the buyer API died mid-call; the scripted offline")
        L.append("  persona finished the call. The rep still grades, compare away.")
        L.append("")
    L.append(_brief_card(rep))
    L.append("")
    L.append("THE FIVE CRITERIA")
    for c in rep.criteria:
        L.append(f"  [{c.level:<6}] {c.name}")
        L.append(f"           {c.detail}")
        if c.evidence:
            L.append(f"           {c.evidence}")
    L.append("")
    L.append("YOUR MEASURED FAILURE MODES")
    for lk in rep.leaks:
        L.append(f"  {lk.label}")
        L.append(f"      {lk.value}  ->  {lk.verdict}")
    L.append("")
    L.append("-" * 72)
    L.append(f"  {rep.score_line}")
    L.append(f"  WOULD THEY BOOK?  {rep.verdict}")
    L.append("-" * 72)
    L.append("")
    L.append("FIX THESE FIRST (next rep):")
    for i, item in enumerate(rep.coach_first, 1):
        L.append(f"  {i}. {item}")
    return "\n".join(L)


def render_markdown(rep: RiqReport, session_id: str, wav_name: str = "") -> str:
    L = [f"# RIQ cold call debrief [{rep.brief_id}] - Session {session_id}", ""]
    if rep.fallback:
        L.append("> **FALLBACK** — the buyer API died mid-call; the scripted "
                 "offline persona finished this call.")
        L.append("")
    L.append(f"- **Buyer:** {rep.persona}")
    L.append(f"- **Difficulty:** {rep.difficulty}")
    if rep.model:
        L.append(f"- **Buyer model:** {rep.model}")
    L.append(f"- **Result:** {rep.score_line}")
    L.append(f"- **Verdict:** {rep.verdict}")
    if wav_name:
        L.append(f"- **Audio:** `{wav_name}`")
    L.append("")
    L.append("## The brief you dialed against")
    L.append("")
    L.append("```")
    L.extend(_brief_card(rep).splitlines())
    L.append("```")
    L.append("")
    L.append("## The five criteria")
    L.append("")
    L.append("| Criterion | Level | Detail |")
    L.append("| --- | --- | --- |")
    for c in rep.criteria:
        L.append(f"| {c.name} | **{c.level}** | {c.detail} |")
    L.append("")
    for c in rep.criteria:
        if c.evidence:
            L.append(f"**{c.name}** &mdash; {c.evidence}")
            L.append("")
    L.append("## Your measured failure modes")
    L.append("")
    L.append("| Metric | Measured | Verdict |")
    L.append("| --- | --- | --- |")
    for lk in rep.leaks:
        L.append(f"| {lk.label} | {lk.value} | {lk.verdict} |")
    L.append("")
    L.append("## Fix these first")
    L.append("")
    for i, item in enumerate(rep.coach_first, 1):
        L.append(f"{i}. {item}")
    L.append("")
    L.append("## Full transcript")
    L.append("")
    for t in rep.turns:
        if t.pm_line:
            L.append(f"**{rep.buyer} (buyer):** {t.pm_line}")
            L.append("")
        timing = []
        if t.onset_latency is not None:
            timing.append(f"first word after {t.onset_latency:.1f}s")
        if t.duration:
            timing.append(f"{t.duration:.0f}s")
        if t.internal_gaps:
            timing.append("gaps: " + ", ".join(f"{g:.1f}s" for g in t.internal_gaps))
        meta = f"  _({'; '.join(timing)})_" if timing else ""
        L.append(f"**YOU:** {t.text or '[silence]'}{meta}")
        L.append("")
    return "\n".join(L)
