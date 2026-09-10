"""
Paraphrase drill: say the same thing a different way, every single time.

The other modes reward getting the right line out fast, which is why twelve reps
produced a forty-word opener recited verbatim in five of them. Fast recall of a
fixed sentence is exactly what "you sounded scripted" means.

This mode inverts the reward. Each shot must still carry the idea (the concept
checks below are the same ones the grader uses), but any phrasing that collides
with something already said is rejected. The bank persists across sessions, so by
the twentieth attempt every easy wording is gone and the idea has to survive
without its sentence.

    python mock_call.py --paraphrase                    # opener, 10 shots
    python mock_call.py --paraphrase --beat hook
    python mock_call.py --paraphrase --beat all --reps 14
    python mock_call.py --paraphrase --list-beats
    python mock_call.py --paraphrase --text             # type instead of speak
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import grader
from profiles import PROFILE, Beat, DEFAULT_PROFILE, get_profile

ROOT = Path(__file__).resolve().parent
# Overridable so the CLI tests can't append to the real sessions/ or the bank.
SESSIONS = Path(os.environ.get("MOCKCALL_SESSIONS") or (ROOT / "sessions"))
BANK_PATH = SESSIONS / "paraphrase_bank.json"

FRESH, RECITED, LOST, FROZE = "FRESH", "RECITED", "LOST IDEA", "FROZE"

# A run of this many identical content words in a row counts as recitation.
MAX_SHARED_RUN = 5
# Content-word overlap above this counts as the same phrasing reshuffled.
JACCARD_LIMIT = 0.70

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "so", "if", "then", "than", "that",
    "this", "these", "those", "is", "are", "was", "were", "be", "been", "being",
    "am", "do", "does", "did", "doing", "have", "has", "had", "of", "to", "in",
    "on", "at", "for", "with", "from", "by", "as", "it", "its", "i", "im", "ive",
    "id", "ill", "me", "my", "you", "your", "youre", "youve", "we", "us", "our",
    "he", "she", "they", "them", "there", "here", "not", "no", "just", "very",
    "really", "s", "t", "re", "ve", "ll", "m", "d", "up", "out", "about", "into",
    "over", "any", "some", "all", "can", "could", "would", "will", "want",
    "um", "uh", "erm", "like", "know", "mean", "kind", "sort", "basically",
    "okay", "ok", "yeah", "yep", "well", "gonna", "going", "got", "get",
    # contraction forms, after apostrophes are stripped. Without these a span
    # like "i'll ... you don't ... and i'm" reads as four content words and
    # pushes genuinely different wordings over the recitation threshold.
    "dont", "thats", "wont", "didnt", "cant", "isnt", "arent", "wasnt",
    "werent", "havent", "hasnt", "hadnt", "doesnt", "wouldnt", "couldnt",
    "shouldnt", "theyre", "theyve", "theres", "whats", "lets", "hes", "shes",
    "youll", "youd", "weve", "were", "wed", "thats", "aint", "gotta", "wanna",
}


def _words(text: str) -> List[str]:
    """Lowercase word list with apostrophes removed, so \"don't\" -> \"dont\"."""
    flat = (text or "").lower().replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9 ]", " ", flat).split()


def content_words(text: str) -> List[str]:
    return [w for w in _words(text) if w not in STOPWORDS]


def longest_shared_run(a: Sequence[str], b: Sequence[str]) -> Tuple[int, List[str]]:
    """Longest contiguous run of identical items. Classic DP, small inputs."""
    if not a or not b:
        return 0, []
    best, end_i = 0, 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, end_i = cur[j], i
        prev = cur
    return best, list(a[end_i - best:end_i])


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# --------------------------------------------------------------------------
# Beats -- what idea has to survive the rewording
# (Beat is defined in profiles.py and imported above.)
# --------------------------------------------------------------------------

BEATS: Dict[str, Beat] = {
    "opener": Beat(
        id="opener",
        label="Permissive-interruption opener",
        cue="Mike Delaney.",
        instruction="Cold open. Admit the interruption, ask for the time, give him an out.",
        concepts={
            "admits the cold call": r"\bdon'?t know me\b|\bnever met\b|\bout of the blue\b"
                                    r"|\bcold call\b|\bweren'?t expecting\b|\bstranger\b"
                                    r"|\brandom\b|\bno idea who\b|\bnot expecting\b"
                                    r"|\binterrupt|\bmiddle of your\b|\bunannounced\b",
            "asks for the time": r"\bcan i\b|\bmind if\b|\bgive me\b|\blet me\b|\bspare\b"
                                 r"|\bseconds?\b|\bminute\b|\bmoment\b|\bhear me\b"
                                 r"|\bworth (a|your|the)\b|\bthirty\b|\b30\b|\btwo minutes\b",
            "offers an escape": r"\btell me\b|\bhang up\b|\bsay no\b|\bkick me\b|\bgo away\b"
                                r"|\bnot for you\b|\bshut me down\b|\blose me\b|\bend the call\b"
                                r"|\bi'?ll go\b|\bi'?m gone\b|\bwrite me off\b|\bcut me off\b",
        },
        min_concepts=2,
        require_question=True,
        seed_turn=1,
    ),
    "hook": Beat(
        id="hook",
        label="Reason for the call (peer reference + real problem)",
        cue="Alright. Thirty seconds. Go ahead.",
        instruction="Why you called: other people like him, and a concrete problem. No features.",
        concepts={
            "peer reference": r"\bother\b|\bpms?\b|\bproject managers?\b|\bgcs?\b"
                              r"|\bgeneral contractors?\b|\bbuilders?\b|\bfirms?\b"
                              r"|\bcompanies\b|\bpeers?\b|\bguys (like|in)\b|\bshops?\b",
            "concrete problem": r"\bdrawing|\brevis|\brfi|\bchange order|\bcloseout|\bclose-out"
                                r"|\bdaily log|\bsubmittal|\bpaper\b|\bbinder|\brework"
                                r"|\bsupersede|\btear ?out|\bas-?built|\bpunch",
        },
        min_concepts=2,
        forbid_capability=True,
        seed_turn=2,
    ),
    "obj_paper": Beat(
        id="obj_paper",
        label="Objection: paper has worked for thirty years",
        cue="We've run jobs on paper for thirty years and it works fine. "
            "I've got binders in my truck that have never once crashed on me.",
        instruction="Acknowledge, reframe, redirect. End on a question. Do not argue.",
        concepts={
            "concedes the point": r"\bfair\b|\bworks?\b|\bnot wrong\b|\bright\b|\bbelieve\b"
                                  r"|\bagree\b|\bthirty years\b|\b30 years\b|\bhear you\b"
                                  r"|\bwon'?t (argue|pretend)\b|\bno argument\b|\brespect\b",
            "his language": r"\bbinder|\bpaper\b|\btruck\b|\bcrew|\bfield\b|\bsuper\b"
                            r"|\bjob\b|\bdrawing|\bset\b|\brfi|\bchange order",
        },
        min_concepts=2,
        require_question=True,
        require_ack=True,
        forbid_capability=True,
        seed_turn=3,
    ),
    "discovery": Beat(
        id="discovery",
        label="Targeted discovery question in his language",
        cue="Yeah, alright. That does happen. We had a crew frame off an old set "
            "on a job last year and it cost us a week.",
        instruction="Ask about his process, using construction nouns. Still no features.",
        concepts={
            "construction artifact": r"\brfi|\bdrawing|\brevis|\bset\b|\bchange order|\bsubmittal"
                                     r"|\bdaily log|\bcloseout|\bclose-out|\bbinder|\bpaper\b"
                                     r"|\bas-?built|\bpunch|\bschedule\b|\blook-?ahead",
            "probe": r"\bhow\b|\bwhat\b|\bwhen\b|\bwhere\b|\bwho\b|\bwalk me\b|\btell me\b"
                     r"|\btalk me\b|\bhelp me understand\b",
        },
        min_concepts=2,
        require_question=True,
        forbid_capability=True,
        seed_turn=4,
    ),
    "cost": Beat(
        id="cost",
        label="Implication question (what the pain costs him)",
        cue="We had a crew on the Dundas job frame off a set the architect had "
            "already revised. Cost us the better part of a week.",
        instruction="Make it cost something. Money, schedule, or who absorbs it.",
        concepts={},
        min_concepts=0,
        require_question=True,
        require_implication=True,
        forbid_capability=True,
        seed_turn=5,
    ),
    "obj_burned": Beat(
        id="obj_burned",
        label="Objection: bought software before, nobody used it",
        cue="We bought a system four years back. Paid for it, sat through the training, "
            "and nobody in the field touched it. I'm not doing that again.",
        instruction="Get curious about what actually failed. Don't defend software.",
        concepts={
            "concedes the point": r"\bfair\b|\bhear you\b|\bbelieve\b|\bdon'?t blame\b"
                                  r"|\bhappens\b|\bcommon\b|\bnot wrong\b|\bwon'?t (argue|pretend)\b"
                                  r"|\bmakes sense\b|\bi bet\b|\bunderstand\b",
            "probes the failure": r"\bwhat happened\b|\bwhich part\b|\bwas it\b|\bfield\b"
                                  r"|\bcrew|\bsuper\b|\brollout\b|\broll ?out\b|\btraining\b"
                                  r"|\badopt|\buse ?d? it\b|\bwhy\b|\bwhere did\b|\bwho (set|ran|led)\b"
                                  r"|\bhow was it\b|\bwhat did\b",
        },
        min_concepts=2,
        require_question=True,
        require_ack=True,
        forbid_capability=True,
        seed_turn=6,
    ),
    "close": Beat(
        id="close",
        label="Close for the AE intro with two specific times",
        cue="Just send me an email and I'll take a look when I get a minute.",
        instruction="Two named times. Not 'sometime next week'.",
        concepts={},
        min_concepts=0,
        min_time_offers=2,
        seed_turn=8,
    ),
}

BEAT_ORDER = ["opener", "hook", "obj_paper", "discovery", "cost", "obj_burned", "close"]

# Procore's construction beats are the module default; expose them through the
# procore profile so profile-driven lookup sees them. generic_saas and other
# profiles carry their own beats from profiles.py.
if "procore" in PROFILE:
    get_profile("procore").beats = BEATS
    get_profile("procore").beat_order = BEAT_ORDER


def beats_for(profile=None):
    """(beats, beat_order) for a profile, falling back to the procore default."""
    if profile is not None and getattr(profile, "beats", None):
        return profile.beats, profile.beat_order or BEAT_ORDER
    return BEATS, BEAT_ORDER


# --------------------------------------------------------------------------
# The bank of things you've already said
# --------------------------------------------------------------------------

class Bank:
    """Everything already said per beat, persisted so novelty accrues across runs."""

    def __init__(self, path: Optional[Path] = None, profile=None):
        if path is None:
            path = BANK_PATH if profile is None else \
                SESSIONS / f"paraphrase_bank_{profile.name}.json"
        self.path = Path(path)
        self.data: Dict[str, List[str]] = {}
        if self.path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self.data = {}

    def entries(self, beat_id: str) -> List[str]:
        return self.data.get(beat_id, [])

    def add(self, beat_id: str, text: str) -> None:
        self.data.setdefault(beat_id, []).append(text)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")

    def seed_from_sessions(self, sessions_dir: Path = SESSIONS) -> int:
        """Harvest what you actually said in past full calls, per beat.

        Without this the first attempt of every beat is trivially 'fresh' -- the
        memorised version would sail through, which is the opposite of the point.
        """
        if not sessions_dir.exists():
            return 0
        by_turn = {b.seed_turn: b.id for b in BEATS.values() if b.seed_turn}
        added = 0
        for folder in sorted(sessions_dir.iterdir()):
            if not folder.is_dir() or folder.name.endswith("-drill"):
                continue
            report = folder / "report.md"
            if not report.exists():
                continue
            says = [s.strip() for s in
                    re.findall(r"\*\*YOU:\*\*(.*)", report.read_text(encoding="utf-8"))]
            for idx, said in enumerate(says, start=1):
                beat_id = by_turn.get(idx)
                if beat_id and said and said != "[silence]":
                    self.add(beat_id, said)
                    added += 1
        return added


# --------------------------------------------------------------------------
# Scoring one shot
# --------------------------------------------------------------------------

@dataclass
class Collision:
    prior: str
    shared_run: List[str]
    overlap: float


@dataclass
class Shot:
    index: int
    beat_id: str
    cue: str
    text: str
    onset_latency: Optional[float]
    froze: bool
    verdict: str
    missing: List[str] = field(default_factory=list)
    collision: Optional[Collision] = None

    @property
    def accepted(self) -> bool:
        return self.verdict == FRESH


def score_shot(
    beat: Beat,
    text: str,
    prior: Sequence[str],
    froze: bool = False,
    max_run: int = MAX_SHARED_RUN,
    jaccard_limit: float = JACCARD_LIMIT,
) -> Tuple[str, List[str], Optional[Collision]]:
    """FROZE / LOST IDEA / RECITED / FRESH, plus why."""
    if froze or not (text or "").strip():
        return FROZE, ["nothing said"], None

    idea_ok, missing = beat.check_idea(text)
    if not idea_ok:
        return LOST, missing, None

    mine = content_words(text)
    worst: Optional[Collision] = None
    for old in prior:
        theirs = content_words(old)
        run_len, run = longest_shared_run(mine, theirs)
        overlap = jaccard(mine, theirs)
        if run_len >= max_run or overlap >= jaccard_limit:
            cand = Collision(prior=old, shared_run=run, overlap=overlap)
            if worst is None or run_len > len(worst.shared_run):
                worst = cand
    if worst is not None:
        return RECITED, [], worst
    return FRESH, [], None


@dataclass
class Summary:
    n: int
    fresh: int
    recited: int
    lost: int
    froze: int
    beats_used: List[str]
    elapsed_s: float

    @property
    def line(self) -> str:
        return (f"PARAPHRASE  {self.fresh}/{self.n} fresh  "
                f"({self.recited} recited, {self.lost} lost the idea, {self.froze} froze)")


def summarize(shots: List[Shot], elapsed_s: float) -> Summary:
    return Summary(
        n=len(shots),
        fresh=sum(1 for s in shots if s.verdict == FRESH),
        recited=sum(1 for s in shots if s.verdict == RECITED),
        lost=sum(1 for s in shots if s.verdict == LOST),
        froze=sum(1 for s in shots if s.verdict == FROZE),
        beats_used=sorted({s.beat_id for s in shots}),
        elapsed_s=elapsed_s,
    )


# --------------------------------------------------------------------------
# Session loop (pure -- `capture` supplies the words, so this is testable)
# --------------------------------------------------------------------------

Capture = Callable[[], Tuple[str, Optional[float], bool]]


def run_session(
    beat_ids: Sequence[str],
    reps: int,
    minutes: float,
    capture: Capture,
    bank: Bank,
    speak_cue: Callable[[Beat, int], None] = lambda b, i: None,
    report: Callable[[Shot], None] = lambda s: None,
    now: Callable[[], float] = time.monotonic,
    max_run: int = MAX_SHARED_RUN,
    jaccard_limit: float = JACCARD_LIMIT,
    beats: Optional[Dict[str, Beat]] = None,
) -> Tuple[List[Shot], Summary]:
    beats = beats or BEATS
    start = now()
    budget = minutes * 60.0
    shots: List[Shot] = []
    for i in range(1, reps + 1):
        if i > 1 and (now() - start) >= budget:
            break
        beat = beats[beat_ids[(i - 1) % len(beat_ids)]]
        speak_cue(beat, i)
        text, onset, froze = capture()
        verdict, missing, collision = score_shot(
            beat, text, bank.entries(beat.id), froze,
            max_run=max_run, jaccard_limit=jaccard_limit,
        )
        shot = Shot(index=i, beat_id=beat.id, cue=beat.cue, text=text,
                    onset_latency=onset, froze=froze, verdict=verdict,
                    missing=missing, collision=collision)
        shots.append(shot)
        # Bank every attempt that carried the idea, accepted or not. A rejected
        # phrasing is still one you reached for, so it should not come back.
        if verdict in (FRESH, RECITED):
            bank.add(beat.id, text)
        report(shot)
    return shots, summarize(shots, now() - start)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

HISTORY_FIELDS = ["session", "shot", "beat", "verdict", "onset", "shared_run",
                  "overlap", "missing", "text"]


def render_markdown(summary: Summary, shots: List[Shot], session_id: str,
                    wav_name: str) -> str:
    L = [f"# Paraphrase drill - {session_id}", ""]
    L.append(f"- **Result:** {summary.line}")
    L.append(f"- **Beats:** {', '.join(summary.beats_used)}")
    L.append(f"- **Elapsed:** {summary.elapsed_s:.0f}s")
    if wav_name:
        L.append(f"- **Audio:** `{wav_name}`")
    L.append("")
    L.append("| Shot | Beat | Verdict | Onset | You said |")
    L.append("| --- | --- | --- | --- | --- |")
    for s in shots:
        onset = "n/a" if s.onset_latency is None else f"{s.onset_latency:.1f}s"
        said = (s.text or "[silence]").replace("|", "/")
        L.append(f"| {s.index} | {s.beat_id} | **{s.verdict}** | {onset} | {said} |")
    L.append("")
    rejected = [s for s in shots if s.verdict in (RECITED, LOST)]
    if rejected:
        L.append("## Why the rejections landed")
        L.append("")
        for s in rejected:
            L.append(f"**Shot {s.index} ({s.beat_id}) - {s.verdict}**")
            L.append("")
            L.append(f"> {s.text}")
            L.append("")
            if s.verdict == LOST:
                L.append(f"- Missing: {'; '.join(s.missing)}")
            elif s.collision:
                run = " ".join(s.collision.shared_run)
                L.append(f"- Reused span: `{run}`")
                L.append(f"- Content overlap: {s.collision.overlap:.0%}")
                L.append(f"- Collided with: {s.collision.prior}")
            L.append("")
    return "\n".join(L)


def append_history(csv_path: Path, session_id: str, shots: List[Shot]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for s in shots:
            w.writerow({
                "session": session_id,
                "shot": s.index,
                "beat": s.beat_id,
                "verdict": s.verdict,
                "onset": "" if s.onset_latency is None else f"{s.onset_latency:.1f}",
                "shared_run": " ".join(s.collision.shared_run) if s.collision else "",
                "overlap": f"{s.collision.overlap:.2f}" if s.collision else "",
                "missing": "; ".join(s.missing),
                "text": s.text,
            })


# --------------------------------------------------------------------------
# Live entry point
# --------------------------------------------------------------------------

def resolve_beats(spec: str, profile=None) -> List[str]:
    beats, order = beats_for(profile)
    if spec == "all":
        return list(order)
    ids = [b.strip() for b in spec.split(",") if b.strip()]
    unknown = [b for b in ids if b not in beats]
    if unknown:
        raise SystemExit(f"unknown beat(s): {', '.join(unknown)}\n"
                         f"available: {', '.join(order)}, all")
    return ids


def list_beats(profile=None) -> None:
    beats, order = beats_for(profile)
    print("Paraphrase beats:\n")
    for bid in order:
        b = beats[bid]
        print(f"  {bid:11} {b.label}")
        print(f"              {b.instruction}")
    print(f"\n  all         cycle through all {len(order)}")


def run_live(args) -> None:
    import sys
    from datetime import datetime

    import numpy as np

    from mock_call import SR, Recorder, Transcriber, Voice

    name = getattr(args, "profile", None) or DEFAULT_PROFILE
    profile = get_profile(name)

    beat_ids = resolve_beats(args.beat, profile)
    bank = Bank(profile=profile)
    if args.reset_bank:
        bank.data = {}
        print("  Bank cleared.")
    seeded = 0
    if not bank.data or args.reseed:
        seeded = bank.seed_from_sessions()

    session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "-para"
    outdir = SESSIONS / profile.name / session_id
    outdir.mkdir(parents=True, exist_ok=True)

    text_mode = args.text
    print()
    print("=" * 72)
    print(f"  PARAPHRASE DRILL  --  {args.reps} shots or {args.minutes} min")
    print("  Same idea every time. Any wording you've used before is rejected.")
    print("=" * 72)
    if seeded:
        print(f"  Seeded the ban list with {seeded} things you already said in past reps.")
    total_banked = sum(len(v) for v in bank.data.values())
    print(f"  Bank now holds {total_banked} phrasings across {len(bank.data)} beats.")
    print(f"  Rejecting: {args.max_run}+ content words in a row, "
          f"or {args.jaccard:.0%} word overlap.")
    print()

    voice = None
    recorder = None
    transcriber = None
    segments: list = []
    pause = np.zeros(0, dtype=np.float32)
    if not text_mode:
        import persona
        voice = Voice(rate=persona.DIFFICULTY_RATE["normal"], enabled=True)
        recorder = Recorder(device=args.device,
                            trailing_silence=min(args.silence, 2.0),
                            max_seconds=25.0)
        transcriber = Transcriber(args.model, beam=1)
        print("  Wear headphones so the mic doesn't pick up his voice.")
        recorder.calibrate()
        transcriber._load()
        pause = np.zeros(int(0.35 * SR), dtype=np.float32)
    print()
    input("  Press ENTER to start... ")
    print()

    def speak_cue(beat: Beat, i: int) -> None:
        print(f"--- shot {i} / {args.reps}   [{beat.id}] {beat.instruction}")
        if beat.cue:
            print(f"MIKE (PM): {beat.cue}")
            if voice is not None:
                segments.append(voice.say(beat.cue))
                segments.append(pause)

    def capture():
        if text_mode:
            said = input("YOU> ").strip()
            return said, None, not said
        rec = recorder.record_turn()
        segments.append(rec.audio)
        segments.append(pause)
        print("  transcribing...", end="", flush=True)
        said = transcriber.transcribe(rec.audio)
        print("\r" + " " * 20 + "\r", end="")
        print(f"YOU: {said or '[silence]'}")
        return said, rec.onset, rec.froze and not said

    def report(shot: Shot) -> None:
        if shot.verdict == FRESH:
            print("  FRESH -- banked, you can't use that one again.")
        elif shot.verdict == RECITED:
            run = " ".join(shot.collision.shared_run) if shot.collision else ""
            print(f"  RECITED -- reused \"{run}\"")
            if shot.collision:
                print(f"            from: {shot.collision.prior[:96]}")
        elif shot.verdict == LOST:
            print(f"  LOST IDEA -- {'; '.join(shot.missing)}")
        else:
            print("  FROZE -- nothing came out.")
        print()

    try:
        shots, summary = run_session(
            beat_ids=beat_ids, reps=args.reps, minutes=args.minutes,
            capture=capture, bank=bank, speak_cue=speak_cue, report=report,
            max_run=args.max_run, jaccard_limit=args.jaccard,
            beats=profile.beats or None,
        )
    except KeyboardInterrupt:
        print("\n  Drill abandoned.\n")
        bank.save()
        sys.exit(130)

    bank.save()
    print(summary.line)
    print(f"  Elapsed: {summary.elapsed_s:.0f}s of {args.minutes * 60:.0f}s budget")
    print()

    wav_name = "session.wav"
    if not text_mode:
        import soundfile as sf
        full = np.concatenate([s for s in segments if s.size]) if segments else np.zeros(1)
        peak = float(np.max(np.abs(full))) or 1.0
        sf.write(str(outdir / wav_name), (full / peak * 0.95).astype(np.float32), SR)
        print(f"  Audio:   {outdir / wav_name}")

    (outdir / "report.md").write_text(
        render_markdown(summary, shots, session_id, wav_name if not text_mode else ""),
        encoding="utf-8",
    )
    append_history(SESSIONS / f"paraphrase_history_{profile.name}.csv", session_id, shots)
    print(f"  Report:  {outdir / 'report.md'}")
    print(f"  History: {SESSIONS / 'paraphrase_history.csv'}")
    print(f"  Bank:    {bank.path}")
    print()
