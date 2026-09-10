"""
Deterministic rubric grader for the Procore SDR mock cold call.

Scores against Procore's five published role-play criteria (relevant industry
language, targeted questions, uncover the pain, book a follow-up, handle
objections) and separately measures the five failure modes diagnosed in
Jason_BDR_Job_Hunt_Feedback: freezing on the opener, talking past objections,
pitching before pain, filling silence, and no live reps.

Nothing here calls a model. Every score is measurable from the transcript and the
audio timings, so the same call always grades the same way and reps are comparable.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import profiles

STRONG, PASS, FAIL = "STRONG", "PASS", "FAIL"


# --------------------------------------------------------------------------
# Vocabulary and phrase banks
# --------------------------------------------------------------------------

# High-value / contextual terms are per-profile (profiles/<name>.high_value_terms
# and .contextual_terms); the rubric reads them from the profile passed to grade().

# Generic SaaS filler. Banned outright in spoken lines by the build spec.
BANNED_PHRASES: Dict[str, str] = {
    "visibility": r"\bvisibility\b",
    "efficiency / efficient": r"\befficienc(?:y|ies)\b|\befficient\b",
    "streamline": r"\bstreamlin(?:e|ed|ing)\b",
    "solution": r"\bsolution(?:s)?\b",
    "pain point(s)": r"\bpain ?point(?:s)?\b",
    "synergy": r"\bsynerg(?:y|ies)\b",
    "game-changer": r"\bgame[- ]?chang(?:er|ing)\b",
    "leverage": r"\bleverag(?:e|ed|ing)\b",
    "seamless": r"\bseamless(?:ly)?\b",
    "robust": r"\brobust\b",
    "best-in-class": r"\bbest[- ]in[- ]class\b",
    "holistic": r"\bholistic\b",
}

FILLER_PHRASES: Dict[str, str] = {
    "um": r"\bum+\b",
    "uh": r"\buh+\b",
    "erm": r"\berm\b",
    "you know": r"\byou know\b",
    "sort of": r"\bsort of\b",
    "kind of": r"\bkind ?of\b|\bkinda\b",
    "basically": r"\bbasically\b",
    "I mean": r"\bi mean\b",
    "literally": r"\bliterally\b",
}

# Acknowledgement -- the first move of Acknowledge -> Reframe -> Redirect.
# Single words only count as the very first word, so "the right data" isn't
# mistaken for conceding the point.
SINGLE_ACKS = {
    "fair", "totally", "yeah", "yep", "yes", "sure", "honestly", "understood",
    "absolutely", "agreed", "right", "ok", "okay", "respect", "true",
}
MULTI_ACKS = (
    "fair enough", "that's fair", "i hear you", "i hear ya", "i get it",
    "makes sense", "that makes sense", "no problem", "of course", "you're right",
    "you're not wrong", "thirty years", "30 years", "i appreciate",
    "i won't pretend", "i'm not going to tell you", "i'm not gonna tell you",
    "i don't blame you", "can't argue", "i believe it", "i bet", "that happens",
    "that tracks", "i won't argue", "no argument",
)

# Pleasantries and permission asks -- real questions, but not *targeted* ones.
# Anchored regexes, so "how are you tracking RFIs?" still counts as discovery
# while "how are you?" does not.
NON_DISCOVERY_QUESTION = (
    # "Is this Mike?" / "Hi, is this Dave?" -- identity checks, not discovery.
    # Kept narrow so "is this something you run into?" still counts.
    r"\bis this (mike|mr\.?|ms\.?|the right person|a good time|a bad time)\b",
    r"^(?:hi|hey|hello|good morning|good afternoon)?[,\s]*is this\s+[\w']+\s*\?$",
    r"\bam i speaking\b",
    r"\bhow are you\s*(doing|today|going)?\s*[?.!]*$",
    r"\bhow'?s it going\b",
    r"\bhow'?(ve|s) you been\b",
    r"\bhow have you been\b",
    r"\bcan i (take|steal|grab|have|get)\s+(a|one|thirty|30|twenty|20|two|couple)\b",
    r"\b(thirty|30|twenty|20|sixty|60)\s+seconds?\b",
    r"\bdo you have\b.*\b(second|minute|moment)s?\b",
    r"\b(got|have)\s+a\s+(minute|second|moment)\b",
    r"\bis now a (bad|good) time\b",
    r"\bbad time\b",
    r"\b(did i|am i) catch(ing)? you\b",
    r"\b(deal|fair|fair enough|right|make sense|makes sense|sound good|ok|okay)\s*\?\s*$",
    r"^is that (fair|right|ok|okay|correct)\b",
)

# Capability / benefit language. Saying any of this before you've asked a
# question is the "pitching before pain" violation.
# "you can <do X>" only counts when it's about using a product. The bare phrase
# appears in the permissive opener ("you can just tell me I'm gone"), which is
# the opposite of a pitch.
PITCH_MARKERS = (
    r"\byou (?:can|could|'d be able to|would be able to) "
    r"(?:see|track|pull|log|find|access|check|view|get|have|run|manage|upload"
    r"|attach|share|send|approve|sign|search|flag|photo)",
    r"\bit (?:lets|let's) you\b", r"\bit tracks\b", r"\bit logs\b",
    r"\bautomatically\b", r"\bin one place\b",
    r"\b(?:the|our|a|one) platform\b", r"\bsoftware platform\b",
    r"\bcopilot\b", r"\bprocore (?:does|handles|gives|lets|will)\b",
    r"\bwith procore\b", r"\bsingle source\b", r"\breal[- ]time\b",
    r"\bdashboard\b", r"\bintegrat", r"\bwe offer\b",
    r"\bour (?:software|product|tool|system)\b", r"\bfeature",
    r"\bwhat we do\b",
)

# Implication questions -- the ones that make the pain cost something. A
# question only counts here if it asks about the *consequence* of a problem:
# money, time, schedule, or who absorbs it. Plain discovery ("how do you track
# RFIs?") is scored separately and must not match.
IMPLICATION_MARKERS = (
    r"\bwhat (does|did|would) (that|it|this)\b",
    r"\bhow much\b",
    r"\bwho (eats|ate|pays|paid|absorbs|absorbed|wears|wore|covers|covered|swallows)\b",
    r"\bwho'?s on the hook\b",
    r"\bwhat happens\b",
    r"\bcost(s|ing)? (for )?(you|your|us|the job|the owner)\b",
    r"\bhow long\b",
    r"\bhow (many|often)\b",
    r"\bdownstream\b", r"\bimpact\b",
    r"\bwhat do you lose\b",
    r"\bwhat'?s that worth\b", r"\bwhat is that worth\b",
    r"\bset (you|us) back\b",
    # construction-specific consequence probes
    r"\bcomes? out of (your|the)\b",
    r"\bout of your (fee|pocket|margin|contingency|float|budget)\b",
    r"\bpush(es|ed)? (substantial completion|the schedule|your (date|schedule|completion))\b",
    r"\bhold(ing)? up (the |your )?(billing|payment|invoice|release|closeout|holdback)\b",
    r"\brefuse to pay\b", r"\b(not|don'?t|didn'?t) get paid\b",
    r"\beat(ing|s)? (that|it|the cost)\b",
    r"\bhow far\b.{0,40}\bbefore\b",
    r"\bstanding around\b", r"\bwaiting on\b", r"\bbuilding ahead\b",
    r"\bevenings (and|or) weekends\b",
    r"\bcome out of\b",
)

PROBE_OPENERS = ("walk me through", "tell me", "talk me through", "help me understand")

DAY_RE = r"\b(?:mon|tues?|wed(?:nes)?|thurs?|fri|sat(?:ur)?|sun)(?:day)?\b|\btomorrow\b|\btoday\b"
CLOCK_RE = (
    r"\b(?:at\s+)?(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|1[0-2]|[1-9])(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?|o'?clock)?\b"
)


# --------------------------------------------------------------------------
# Turn model
# --------------------------------------------------------------------------

@dataclass
class Turn:
    index: int
    stage_id: str
    expects: str
    pm_line: str
    text: str
    onset_latency: Optional[float] = None   # seconds of silence before first word
    duration: float = 0.0                   # seconds recorded
    internal_gaps: List[float] = field(default_factory=list)
    is_objection: bool = False
    objection_label: str = ""
    froze: bool = False

    @property
    def words(self) -> int:
        return len([w for w in re.split(r"\s+", self.text) if w])


@dataclass
class CriterionResult:
    name: str
    level: str
    detail: str
    evidence: str = ""
    key: str = ""            # stable column name for history.csv


@dataclass
class Leak:
    """One measured failure-mode metric.

    `key` is stable across sessions so history.csv keeps a fixed header, while
    `label` can carry run-specific detail (which filler words, which turn).
    """

    key: str
    label: str
    value: str
    verdict: str


# --------------------------------------------------------------------------
# Text helpers (also used by the call loop to branch the persona)
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def is_question(sentence: str) -> bool:
    s = sentence.strip()
    if s.endswith("?"):
        return True
    low = _norm(s)
    return any(low.startswith(p) for p in PROBE_OPENERS)


def count_questions(text: str) -> int:
    return sum(1 for s in sentences(text) if is_question(s))


def has_question(text: str) -> bool:
    return count_questions(text) > 0


def count_discovery_questions(text: str) -> int:
    """Questions about HIS situation. Excludes 'is this Mike?' and permission asks."""
    n = 0
    for s in sentences(text):
        if not is_question(s):
            continue
        low = _norm(s)
        if any(re.search(p, low) for p in NON_DISCOVERY_QUESTION):
            continue
        n += 1
    return n


def is_acknowledged(text: str) -> bool:
    """Did the response open by acknowledging, rather than rebutting?"""
    low = _norm(text)
    if not low:
        return False
    words = low.split()
    if words[0].strip(",.!?'\"") in SINGLE_ACKS:
        return True
    opening = " ".join(words[:14])
    return any(m in opening for m in MULTI_ACKS)


def mentions_capability(text: str) -> bool:
    low = _norm(text)
    return any(re.search(m, low) for m in PITCH_MARKERS)


def has_implication_question(text: str) -> bool:
    low = _norm(text)
    return any(re.search(m, low) for m in IMPLICATION_MARKERS) and has_question(text)


DRILL_FAST_S = 3.0
DRILL_OK_S = 6.0


def score_drill_shot(text: str, onset: Optional[float], froze: bool) -> Tuple[bool, str]:
    """Pain-reveal drill: did a cost question come out, and how fast.

    Returns (hit, verdict) where verdict is FAST | OK | SLOW | HIT | MISS.
    HIT is text-mode (no clock). A slow hit still counts — retrieval, not silence.
    """
    if froze or not has_implication_question(text or ""):
        return False, "MISS"
    if onset is None:
        return True, "HIT"
    if onset <= DRILL_FAST_S:
        return True, "FAST"
    if onset <= DRILL_OK_S:
        return True, "OK"
    return True, "SLOW"


@dataclass
class DrillShot:
    index: int
    pm_line: str
    text: str
    onset_latency: Optional[float]
    froze: bool
    cost_question: bool
    verdict: str


@dataclass
class DrillSummary:
    n: int
    hits: int
    fast: int
    ok: int
    slow: int
    miss: int
    median_onset: Optional[float]
    elapsed_s: float
    reps_requested: int

    @property
    def line(self) -> str:
        med = f"{self.median_onset:.1f}s" if self.median_onset is not None else "n/a"
        return (
            f"DRILL  {self.hits}/{self.n} cost questions  median {med}  "
            f"({self.fast} FAST, {self.ok} OK, {self.slow} SLOW, {self.miss} MISS)"
        )


def summarize_drill(shots: List[DrillShot], elapsed_s: float, reps_requested: int) -> DrillSummary:
    onsets = sorted(
        s.onset_latency for s in shots if s.cost_question and s.onset_latency is not None
    )
    median = None
    if onsets:
        mid = len(onsets) // 2
        median = onsets[mid] if len(onsets) % 2 else (onsets[mid - 1] + onsets[mid]) / 2
    return DrillSummary(
        n=len(shots),
        hits=sum(1 for s in shots if s.cost_question),
        fast=sum(1 for s in shots if s.verdict == "FAST"),
        ok=sum(1 for s in shots if s.verdict in ("OK", "HIT")),
        slow=sum(1 for s in shots if s.verdict == "SLOW"),
        miss=sum(1 for s in shots if s.verdict == "MISS"),
        median_onset=median,
        elapsed_s=elapsed_s,
        reps_requested=reps_requested,
    )


def find_matches(text: str, bank: Dict[str, str]) -> List[str]:
    low = _norm(text)
    return [name for name, pattern in bank.items() if re.search(pattern, low)]


def find_time_offers(text: str) -> List[str]:
    """Pull out concrete meeting-time offers like 'Thursday at 7'."""
    low = _norm(text)
    offers: List[str] = []
    for m in re.finditer(DAY_RE, low):
        window = low[m.start(): m.start() + 70]
        clock = re.search(CLOCK_RE, window[len(m.group(0)):])
        if clock:
            offers.append(f"{m.group(0).strip()} at {clock.group(1)}")
    # de-dupe while keeping order
    seen, out = set(), []
    for o in offers:
        if o not in seen:
            seen.add(o)
            out.append(o)
    return out


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

HISTORY_FIELDS = [
    "session", "difficulty", "criteria_passed", "verdict",
    "c1_industry_language", "c2_targeted_questions", "c3_uncover_pain",
    "c4_book_followup", "c5_handle_objections",
    "opener_latency", "objection_pause", "ack_rate", "pitch_before_pain",
    "filler_rate", "longest_turn", "banned_words", "freezes", "talk_time",
]


@dataclass
class Report:
    criteria: List[CriterionResult]
    leaks: List[Leak]
    verdict: str
    passed_count: int
    coach_first: List[str]
    turns: List[Turn]
    difficulty: str

    @property
    def score_line(self) -> str:
        return f"{self.passed_count}/5 criteria at PASS or better"


def _level(strong: bool, ok: bool) -> str:
    return STRONG if strong else (PASS if ok else FAIL)


def grade(turns: List[Turn], difficulty: str, pain_revealed: bool,
          meeting_booked: bool, profile: Optional[profiles.Profile] = None) -> Report:
    if profile is None:
        profile = profiles.get_profile("procore")
    candidate_turns = [t for t in turns if t.text.strip() or t.froze]
    all_text = " ".join(t.text for t in turns)

    # ---- 1. Relevant industry language -------------------------------------
    hv = find_matches(all_text, profile.high_value_terms)
    ctx = find_matches(all_text, profile.contextual_terms)
    missed = [t for t in list(profile.high_value_terms)[:6] if t not in hv]
    c1 = CriterionResult(
        "Relevant industry language",
        _level(len(hv) >= 5, len(hv) >= 3),
        f"{len(hv)} high-value construction terms used, {len(ctx)} contextual.",
        "Used: " + (", ".join(hv) or "none")
        + ("\n  Missed high-value: " + ", ".join(missed) if missed else ""),
        key="c1_industry_language",
    )

    # ---- 2. Targeted questions ---------------------------------------------
    qcount = sum(count_discovery_questions(t.text) for t in turns)
    turns_with_q = sum(1 for t in turns if count_discovery_questions(t.text))
    c2 = CriterionResult(
        "Ask targeted questions",
        _level(qcount >= 5, qcount >= 3),
        f"{qcount} targeted questions across {turns_with_q} turns "
        f"(permission and 'is this Mike?' don't count).",
        "Target is 3+ real questions about his jobs, spread across the call.",
        key="c2_targeted_questions",
    )

    # ---- 3. Uncover the pain ----------------------------------------------
    impl = [t.index for t in turns if has_implication_question(t.text)]
    c3 = CriterionResult(
        "Uncover the pain",
        _level(pain_revealed and bool(impl), pain_revealed),
        ("He named a real headache in his own words."
         if pain_revealed else "He never gave up a concrete problem."),
        (f"Implication question(s) on turn(s): {', '.join(map(str, impl))}"
         if impl else "No implication question -- you never made the pain cost anything."),
        key="c3_uncover_pain",
    )

    # ---- 4. Book a follow-up ---------------------------------------------
    offers: List[str] = []
    for t in turns:
        offers.extend(o for o in find_time_offers(t.text) if o not in offers)
    c4 = CriterionResult(
        "Book a follow-up conversation",
        _level(len(offers) >= 2 and meeting_booked, len(offers) >= 2),
        f"{len(offers)} specific time(s) offered; meeting "
        f"{'BOOKED' if meeting_booked else 'not booked'}.",
        "Offered: " + (", ".join(offers) or "none -- you never named a time"),
        key="c4_book_followup",
    )

    # ---- 5. Handle objections --------------------------------------------
    obj_turns = [t for t in turns if t.is_objection]
    handled, obj_detail = 0, []
    for t in obj_turns:
        ack, q = is_acknowledged(t.text), has_question(t.text)
        if ack and q:
            handled += 1
        obj_detail.append(
            f"'{t.objection_label}': "
            f"{'acknowledged' if ack else 'NO acknowledgement'}, "
            f"{'handed back with a question' if q else 'NO question at the end'}"
        )
    total_obj = len(obj_turns) or 1
    c5 = CriterionResult(
        "Handle objections (Ack -> Reframe -> Redirect)",
        _level(handled == len(obj_turns) and obj_turns, handled >= max(1, len(obj_turns) - 1)),
        f"{handled}/{len(obj_turns)} objections fully handled.",
        "\n  ".join(obj_detail) or "No objections reached.",
        key="c5_handle_objections",
    )

    criteria = [c1, c2, c3, c4, c5]
    passed = sum(1 for c in criteria if c.level in (PASS, STRONG))

    # ---- Leak metrics (the five diagnosed failure modes) ------------------
    leaks: List[Leak] = []

    opener = turns[0] if turns else None
    if opener and opener.onset_latency is not None:
        lat = opener.onset_latency
        leaks.append(Leak(
            "opener_latency", "Freezing on the opener (time to first word)",
            f"{lat:.1f}s",
            "GOOD" if lat <= 1.5 else ("WATCH" if lat <= 3.0 else "LEAK"),
        ))

    obj_lats = [t.onset_latency for t in obj_turns if t.onset_latency is not None]
    if obj_lats:
        avg = sum(obj_lats) / len(obj_lats)
        if avg < 0.6:
            pause_verdict = "LEAK (you cut in -- let the objection land)"
        elif avg <= 3.0:
            pause_verdict = "GOOD (you paused before answering)"
        else:
            pause_verdict = "WATCH (long freeze before answering)"
        leaks.append(Leak("objection_pause", "Pause before answering an objection",
                          f"{avg:.1f}s avg", pause_verdict))

    ack_rate = handled / total_obj
    leaks.append(Leak(
        "ack_rate", "Talking past objections (acknowledged first)",
        f"{int(ack_rate * 100)}%",
        "GOOD" if ack_rate == 1 else ("WATCH" if ack_rate >= 0.66 else "LEAK"),
    ))

    # Pitching before pain: how many questions landed before the first capability claim
    first_pitch = next((t.index for t in turns if mentions_capability(t.text)), None)
    q_before = sum(count_discovery_questions(t.text) for t in turns
                   if first_pitch is None or t.index < first_pitch)
    if first_pitch is None:
        pitch_verdict, pitch_val = "GOOD (no premature capability claims)", "n/a"
    elif q_before >= 2:
        pitch_verdict, pitch_val = "GOOD", f"{q_before} questions first"
    elif q_before == 1:
        pitch_verdict, pitch_val = "WATCH", "only 1 question first"
    else:
        pitch_verdict, pitch_val = (
            f"LEAK (capability claim on turn {first_pitch} before asking anything)",
            "0 questions first",
        )
    leaks.append(Leak("pitch_before_pain", "Pitching before pain", pitch_val, pitch_verdict))

    total_words = sum(t.words for t in turns) or 1
    fillers = {name: len(re.findall(p, _norm(all_text)))
               for name, p in FILLER_PHRASES.items()}
    filler_total = sum(fillers.values())
    rate = filler_total / total_words * 100
    top = ", ".join(f"{k}x{v}" for k, v in sorted(fillers.items(), key=lambda kv: -kv[1]) if v)
    leaks.append(Leak(
        "filler_rate",
        f"Filling silence (filler words{': ' + top if top else ''})",
        f"{filler_total} in {total_words} words ({rate:.1f}/100)",
        "GOOD" if rate < 3 else ("WATCH" if rate < 6 else "LEAK"),
    ))

    longest = max(turns, key=lambda t: t.words) if turns else None
    if longest:
        leaks.append(Leak(
            "longest_turn",
            f"Longest single turn (turn {longest.index}, monologue check)",
            f"{longest.words} words",
            "GOOD" if longest.words <= 130 else "WATCH (you're monologuing)",
        ))

    banned_hits = []
    for t in turns:
        for name in find_matches(t.text, BANNED_PHRASES):
            banned_hits.append(f"turn {t.index}: {name}")
    leaks.append(Leak(
        "banned_words", "Generic SaaS filler (banned words)",
        f"{len(banned_hits)} hit(s)",
        "GOOD" if not banned_hits else "LEAK: " + "; ".join(banned_hits),
    ))

    freezes = [t.index for t in turns if t.froze]
    leaks.append(Leak(
        "freezes", "Dead-air freezes",
        f"turns {', '.join(map(str, freezes))}" if freezes else "none",
        "LEAK" if freezes else "GOOD",
    ))

    talk = sum(t.duration for t in turns)
    leaks.append(Leak("talk_time", "Your total talk time", f"{talk:.0f}s", "info"))

    # ---- Verdict ---------------------------------------------------------
    hard_fail = pitch_verdict.startswith("LEAK")
    if passed >= 4 and not hard_fail:
        verdict = "YES -- this reads like someone who could take a real call next week."
    elif passed >= 3:
        verdict = "NOT YET -- the shape is there but it would cost you the round."
    else:
        verdict = "NO -- this call would end the interview. Run it again."

    # ---- What to fix first ----------------------------------------------
    coach: List[str] = []
    for c in criteria:
        if c.level == FAIL:
            coach.append(f"{c.name}: {c.detail}")
    for lk in leaks:
        if lk.verdict.startswith("LEAK"):
            coach.append(f"{lk.label} ({lk.value})")
    if not coach:
        coach.append("Nothing failed. Push for STRONG on the criteria still at PASS.")

    return Report(criteria, leaks, verdict, passed, coach[:3], turns, difficulty)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_console(rep: Report) -> str:
    L = []
    L.append("=" * 72)
    L.append(f"  SCORECARD  --  difficulty: {rep.difficulty}")
    L.append("=" * 72)
    L.append("")
    L.append("PROCORE'S FIVE PUBLISHED CRITERIA")
    for c in rep.criteria:
        L.append(f"  [{c.level:<6}] {c.name}")
        L.append(f"           {c.detail}")
        if c.evidence:
            for line in c.evidence.split("\n"):
                L.append(f"           {line.strip()}")
    L.append("")
    L.append("YOUR MEASURED FAILURE MODES")
    for lk in rep.leaks:
        L.append(f"  {lk.label}")
        L.append(f"      {lk.value}  ->  {lk.verdict}")
    L.append("")
    L.append("-" * 72)
    L.append(f"  {rep.score_line}")
    L.append(f"  WOULD REENA BUY IT?  {rep.verdict}")
    L.append("-" * 72)
    L.append("")
    L.append("FIX THESE FIRST (next rep):")
    for i, item in enumerate(rep.coach_first, 1):
        L.append(f"  {i}. {item}")
    return "\n".join(L)


def render_markdown(rep: Report, session_id: str, wav_name: str) -> str:
    L = [f"# Mock Cold Call - Session {session_id}", ""]
    L.append(f"- **Difficulty:** {rep.difficulty}")
    L.append(f"- **Result:** {rep.score_line}")
    L.append(f"- **Verdict:** {rep.verdict}")
    L.append(f"- **Audio:** `{wav_name}`")
    L.append("")
    L.append("## Procore's five published criteria")
    L.append("")
    L.append("| Criterion | Level | Detail |")
    L.append("| --- | --- | --- |")
    for c in rep.criteria:
        L.append(f"| {c.name} | **{c.level}** | {c.detail} |")
    L.append("")
    for c in rep.criteria:
        if c.evidence:
            L.append(f"**{c.name}** &mdash; {c.evidence.replace(chr(10), ' ')}")
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
        L.append(f"**MIKE (PM):** {t.pm_line}")
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
        L.append(f"> _Expected here: {t.expects}_")
        L.append("")
    return "\n".join(L)


def append_history(csv_path: Path, session_id: str, rep: Report) -> None:
    """One row per rep so improvement is visible across sessions.

    Uses the fixed HISTORY_FIELDS header, so run-specific detail in a metric
    label can never shift the columns between sessions.
    """
    new = not csv_path.exists()
    row = {f: "" for f in HISTORY_FIELDS}
    row.update({
        "session": session_id,
        "difficulty": rep.difficulty,
        "criteria_passed": rep.passed_count,
        "verdict": rep.verdict.split("--")[0].strip(),
    })
    for c in rep.criteria:
        if c.key in row:
            row[c.key] = c.level
    for lk in rep.leaks:
        if lk.key in row:
            row[lk.key] = lk.value
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


DRILL_HISTORY_FIELDS = [
    "session", "shot", "verdict", "cost_question", "onset", "elapsed_s", "text", "cue",
]


def render_drill_markdown(
    summary: DrillSummary, shots: List[DrillShot], session_id: str, wav_name: str,
) -> str:
    L = [f"# Pain-reveal drill - {session_id}", ""]
    L.append(f"- **Result:** {summary.line}")
    L.append(f"- **Elapsed:** {summary.elapsed_s:.0f}s")
    if wav_name:
        L.append(f"- **Audio:** `{wav_name}`")
    L.append("")
    L.append("| Shot | Verdict | Onset | You said |")
    L.append("| --- | --- | --- | --- |")
    for s in shots:
        onset = "n/a" if s.onset_latency is None else f"{s.onset_latency:.1f}s"
        you = (s.text or "[silence]").replace("|", "/")
        L.append(f"| {s.index} | **{s.verdict}** | {onset} | {you} |")
    L.append("")
    for s in shots:
        L.append(f"**Cue {s.index}:** {s.pm_line}")
        L.append("")
    return "\n".join(L)


def append_drill_history(
    csv_path: Path, session_id: str, shots: List[DrillShot], elapsed_s: float,
) -> None:
    """One row per drill shot. Never write sessions/history.csv from here."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DRILL_HISTORY_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for s in shots:
            onset = "" if s.onset_latency is None else f"{s.onset_latency:.1f}"
            w.writerow({
                "session": session_id,
                "shot": s.index,
                "verdict": s.verdict,
                "cost_question": "Y" if s.cost_question else "N",
                "onset": onset,
                "elapsed_s": f"{elapsed_s:.1f}",
                "text": s.text,
                "cue": s.pm_line,
            })
