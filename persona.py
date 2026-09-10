"""The prospect, sourced from the active profile.

Persona data now lives in profiles (per-company). This module keeps the
Procore-specific construction builder and a set of deprecated constant aliases
so the old call sites keep working while the engine migrates onto profiles.
New call sites should read from profiles.get_profile(...) instead.
"""
from __future__ import annotations

import random
from typing import List

from profiles import PROFILE, Stage, get_profile, build_script as generic_build_script

# Deprecated: all of these are Procore (construction) values for backward
# compatibility. Prefer profiles.get_profile("procore") going forward.
_PROCORE = get_profile("procore")

PM_NAME = _PROCORE.buyer_name
PM_COMPANY = _PROCORE.company
DIFFICULTIES = ("normal", "hostile", "apathetic", "timepoor")
DIFFICULTY_RATE = _PROCORE.difficulty_rates
PICKUP = _PROCORE.pickup
REACT_OPENER = _PROCORE.react_opener
OBJ_PAPER = _PROCORE.objection_pools["status_quo"]
OBJ_BURNED = _PROCORE.objection_pools["burned"]
OBJ_CLOSE = _PROCORE.objection_pools["close"]
OBJ_CLOSE_ALT = _PROCORE.objection_pools["close_alt"]
PAIN_REVEAL = _PROCORE.pain_reveal
PAIN_DRILL_CUES = _PROCORE.pain_drill_cues
FREEZE_PROMPTS = _PROCORE.freeze_prompts
SIGN_OFF = _PROCORE.sign_off


def _procore_script(difficulty: str, rng: random.Random,
                    profile=None) -> List[Stage]:
    """The original Procore construction call. Kept byte-identical: stage ids
    include 'obj_paper' which mock_call._landed and regrade depend on."""
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"unknown difficulty {difficulty!r}")

    good_open, poor_open = REACT_OPENER[difficulty]
    close_pool = list(OBJ_CLOSE) + (list(OBJ_CLOSE_ALT) if rng.random() < 0.35 else [])

    return [
        Stage(
            id="pickup",
            expects="Your two-sentence permissive-interruption opener, said cold.",
            good=PICKUP[difficulty],
            coach_note="Freezing here is your #1 documented leak. Opener must be automatic.",
        ),
        Stage(
            id="react_opener",
            expects="Your R+I hook: external fact + internal signal, peer-referenced. "
                    "Then the long pause.",
            good=good_open,
            poor=poor_open,
            coach_note="Landed = you asked permission. Poor = you launched in without it.",
        ),
        Stage(
            id="obj_paper",
            expects="Acknowledge -> Reframe -> Redirect, ending on a question. Do not argue.",
            good=rng.choice(OBJ_PAPER),
            is_objection=True,
            objection_label="paper for 30 years",
            coach_note="Pause ~1s before you answer. Acknowledge the kernel of truth first.",
        ),
        Stage(
            id="react_handle_1",
            expects="Two or three targeted discovery questions in his language. No features yet.",
            good="Yeah, alright. That does happen. We had a crew frame off an old set on a "
                 "job last year and it cost us a week.",
            poor="You're not really answering me. This sounds like every other software call "
                 "I get.",
            coach_note="He opens up only if you acknowledged him instead of pitching.",
        ),
        Stage(
            id="pain_reveal",
            expects="Follow the thread. One implication question -- what is it costing him?",
            good=rng.choice(PAIN_REVEAL),
            poor="I mean, it's fine. We manage. Everybody's got headaches.",
            coach_note="This is the pain you were sent to uncover. Do not pitch over it.",
        ),
        Stage(
            id="obj_burned",
            expects="Get curious about WHAT failed. Don't defend software. Don't bash the vendor.",
            good=rng.choice(OBJ_BURNED),
            is_objection=True,
            objection_label="burned by tech / nobody used it",
            coach_note="The heart of the brief. Ask whether it was the tool or the rollout.",
        ),
        Stage(
            id="react_handle_2",
            expects="Value in field terms -- field usability + phased start. Then move to the close.",
            good="That's fair. It was the field, mostly. My super hated it, said it took him "
                 "twice as long on his phone as it did on paper.",
            poor="See, this is what I mean. You're already selling me the thing.",
            coach_note="Landed = you got curious. Poor = you defended the software.",
        ),
        Stage(
            id="obj_close",
            expects="Close for the AE intro with TWO specific times.",
            good=rng.choice(close_pool),
            is_objection=True,
            objection_label="brush-off at the close",
            coach_note="Two named times, or he walks. This is the objective of the call.",
        ),
        Stage(
            id="resolution",
            expects="Confirm the email, set a one-line agenda, ask what he wants covered.",
            good="Fine. Thursday at seven works, before the crews roll. Send the invite to "
                 "m.delaney at the office. And tell your guy I want to know how it handles "
                 "change orders, because that's my headache.",
            poor="Yeah, just send me the email. I've got to go.",
            coach_note="He only says yes if you offered two specific times.",
        ),
    ]


# Exposed as `persona.build_script(difficulty, rng, profile=None)`.
# A profile that declares no custom builder falls back to the generic builder.
def build_script(difficulty: str, rng: random.Random,
                 profile=None) -> List[Stage]:
    if profile is None:
        profile = _PROCORE
    if profile is _PROCORE:
        return _procore_script(difficulty, rng)
    return generic_build_script(difficulty, rng, profile)


def pain_drill_cues(n: int, rng: random.Random, profile=None) -> List[str]:
    if profile is None:
        profile = _PROCORE
    order = list(profile.pain_drill_cues)
    rng.shuffle(order)
    return [order[i % len(order)] for i in range(n)]


# Bind the Procore profile to its original construction builder (not the
# generic one) so behavior is byte-identical.
_PROCORE.build_script = _procore_script
