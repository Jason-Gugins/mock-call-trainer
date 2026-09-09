"""Paraphrase drill checks.

The whole point of this mode is that Jason's memorised lines get rejected and a
genuine rewording of the same idea gets through. If those two facts ever stop
holding, the drill is training the wrong thing again.

    python tests/test_paraphrase.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paraphrase as P
from paraphrase import BEATS, FRESH, FROZE, LOST, RECITED, Bank, Shot

# The 40-word block that came out verbatim in 5 of 12 recorded reps.
MEMORISED_OPENER = (
    "Mike, I'll be straight with you, you don't know me and I'm jumping right "
    "into the middle of your day. Can I take 30 seconds to tell you why I "
    "called, and if it's not for you, you can just tell me I'm gone?"
)

failures: list[str] = []
checks = 0


def check(label: str, got, want) -> None:
    global checks
    checks += 1
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def verdict(beat_id: str, text: str, prior=()) -> str:
    v, _missing, _c = P.score_shot(BEATS[beat_id], text, list(prior))
    return v


# --------------------------------------------------------------------------
# 1. Novelty machinery
# --------------------------------------------------------------------------

check("shared run, identical",
      P.longest_shared_run(["a", "b", "c"], ["a", "b", "c"])[0], 3)
check("shared run, none",
      P.longest_shared_run(["a", "b"], ["c", "d"])[0], 0)
check("shared run finds the middle",
      P.longest_shared_run(list("xabcy"), list("zabcw"))[1], ["a", "b", "c"])
check("jaccard identical", P.jaccard(["a", "b"], ["a", "b"]), 1.0)
check("jaccard disjoint", P.jaccard(["a"], ["b"]), 0.0)
check("stopwords stripped from content words",
      P.content_words("I am going to the site"), ["site"])


# --------------------------------------------------------------------------
# 2. The memorised opener must be rejected once it is in the bank
# --------------------------------------------------------------------------

check("memorised opener passes the idea check on its own",
      verdict("opener", MEMORISED_OPENER), FRESH)
check("memorised opener is RECITED when already banked",
      verdict("opener", MEMORISED_OPENER, [MEMORISED_OPENER]), RECITED)

# Trivial edits must not sneak it through.
check("reordered but same words is still RECITED",
      verdict("opener",
              "Mike, you don't know me and I'm jumping right into the middle of "
              "your day, so can I take 30 seconds to tell you why I called? If "
              "it's not for you just tell me I'm gone.",
              [MEMORISED_OPENER]),
      RECITED)
check("swapping one word is still RECITED",
      verdict("opener",
              "Mike, I'll be honest with you, you don't know me and I'm jumping "
              "right into the middle of your day. Can I take 30 seconds to tell "
              "you why I called, and if it's not for you, just tell me I'm gone?",
              [MEMORISED_OPENER]),
      RECITED)


# --------------------------------------------------------------------------
# 3. A real rewording of the same idea must get through
# --------------------------------------------------------------------------

FRESH_OPENERS = [
    "Mike, this is a cold call and you weren't expecting me. Worth a minute to "
    "hear why I picked up the phone, or should I let you go?",
    "You have no idea who I am and I picked a terrible moment. Mind if I give "
    "you one sentence and you decide whether I keep going?",
    "Total stranger calling out of the blue here. Can you spare me about twenty "
    "seconds before you write me off?",
]
for i, line in enumerate(FRESH_OPENERS, start=1):
    check(f"genuine rewording {i} is FRESH",
          verdict("opener", line, [MEMORISED_OPENER]), FRESH)

# They must also block each other, so the bank keeps biting.
check("two different fresh openers still collide with themselves",
      verdict("opener", FRESH_OPENERS[0], [FRESH_OPENERS[0]]), RECITED)
check("fresh opener 2 does not collide with fresh opener 1",
      verdict("opener", FRESH_OPENERS[1], [FRESH_OPENERS[0]]), FRESH)


# --------------------------------------------------------------------------
# 4. Novel wording that loses the idea must fail
# --------------------------------------------------------------------------

check("no question is LOST",
      verdict("opener",
              "Nobody here knows me and I picked a bad moment to call you."),
      LOST)
check("word salad is LOST",
      verdict("opener", "Purple mountain bicycle vegetables, quite frankly?"), LOST)
check("silence is FROZE", verdict("opener", ""), FROZE)
check("froze flag wins",
      P.score_shot(BEATS["opener"], "anything", [], froze=True)[0], FROZE)


# --------------------------------------------------------------------------
# 5. Beat-specific requirements survive rewording pressure
# --------------------------------------------------------------------------

check("close needs two times",
      verdict("close", "Could we grab fifteen minutes sometime next week?"), LOST)
check("close with two times is FRESH",
      verdict("close",
              "I'd rather not add to your inbox. Thursday at seven before the "
              "crews roll, or Friday at four after your job walk?"),
      FRESH)

check("plain discovery does not satisfy the cost beat",
      verdict("cost", "How are you tracking drawing revisions right now?"), LOST)
check("consequence question satisfies the cost beat",
      verdict("cost", "Who ate that week, you or the owner?"), FRESH)

check("rebuttal without acknowledging is LOST",
      verdict("obj_paper",
              "Paper can't tell your crew a drawing changed. How do you handle that?"),
      LOST)
check("acknowledge then redirect is FRESH",
      verdict("obj_paper",
              "Fair enough, and binders don't crash. When a drawing gets revised "
              "though, how does the crew in the field find out?"),
      FRESH)

check("defending the software on the burned objection is LOST",
      verdict("obj_burned",
              "I hear you, but our platform is different and the field can "
              "actually use it. Does that make sense?"),
      LOST)
check("getting curious about the failure is FRESH",
      verdict("obj_burned",
              "I don't blame you at all. Was it the tool itself, or was it how "
              "the rollout landed with your field guys?"),
      FRESH)

check("hook that pitches a capability is LOST",
      verdict("hook",
              "Other PMs use Procore so you can see every drawing revision "
              "automatically in one place."),
      LOST)
check("hook with peers plus a real problem is FRESH",
      verdict("hook",
              "I've been on the phone with other project managers at GCs around "
              "here, and the thing that keeps surfacing is crews building off "
              "superseded drawings."),
      FRESH)


# --------------------------------------------------------------------------
# 6. Bank accrual and seeding
# --------------------------------------------------------------------------

bank = Bank(path=Path("/nonexistent/bank.json"))
check("empty bank has no entries", bank.entries("opener"), [])
bank.add("opener", MEMORISED_OPENER)
check("bank stores one", len(bank.entries("opener")), 1)

shots, summary = P.run_session(
    beat_ids=["opener"],
    reps=3,
    minutes=99,
    capture=iter([
        (MEMORISED_OPENER, 0.4, False),      # already banked -> RECITED
        (FRESH_OPENERS[0], 0.5, False),      # new -> FRESH
        (FRESH_OPENERS[0], 0.5, False),      # repeat of shot 2 -> RECITED
    ]).__next__,
    bank=bank,
    now=iter([0.0, 1.0, 2.0, 3.0, 4.0]).__next__,
)
check("session produced 3 shots", len(shots), 3)
check("shot 1 recited", shots[0].verdict, RECITED)
check("shot 2 fresh", shots[1].verdict, FRESH)
check("repeating your own fresh line is rejected", shots[2].verdict, RECITED)
check("summary counts fresh", summary.fresh, 1)
check("summary counts recited", summary.recited, 2)

# Seeding from the real session folder should find his actual turns.
real = Bank(path=Path("/nonexistent/bank2.json"))
n = real.seed_from_sessions(Path(__file__).resolve().parent.parent / "sessions")
check("seeding harvested something", n > 0, True)
check("seeded the opener beat", len(real.entries("opener")) > 0, True)
if n:
    v = verdict("opener", MEMORISED_OPENER, real.entries("opener"))
    check("his real opener is rejected by the seeded bank", v, RECITED)

# Reporting must not explode on any verdict.
md = P.render_markdown(summary, shots, "test", "session.wav")
check("markdown mentions the reused span", "Reused span" in md, True)
check("markdown has a row per shot", md.count("\n| 1 |"), 1)


# --------------------------------------------------------------------------

print()
if failures:
    print(f"FAILED {len(failures)} of {checks}")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"All {checks} paraphrase checks passed.")
