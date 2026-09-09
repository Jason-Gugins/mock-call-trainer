"""
The prospect: Mike Delaney, Senior Project Manager at a mid-size GTA general contractor.

Persona per Procore's role-play brief: influential but skeptical, burned by tech
before, runs every job on pen and paper, and it's causing him real headaches.

The call is a fixed sequence of stages. At each stage the PM picks a line variant
based on how the candidate's last turn actually scored, so the prospect gets warmer
when you handle him well and colder when you don't. No LLM involved -- the branching
is driven by the same deterministic checks the grader uses.
"""

from dataclasses import dataclass, field
from typing import Dict, List
import random

PM_NAME = "Mike Delaney"
PM_COMPANY = "Delaney Construction Group"

DIFFICULTIES = ("normal", "hostile", "apathetic", "timepoor")

# Speech rate for the Windows SAPI voice (-10..10). Faster = more pressure.
DIFFICULTY_RATE = {"normal": 0, "hostile": 2, "apathetic": -1, "timepoor": 3}


@dataclass
class Stage:
    """One PM turn, plus what the candidate is expected to do in response."""

    id: str
    expects: str                      # what good looks like from the candidate next
    good: str                         # PM line if the previous turn landed
    poor: str = ""                    # PM line if it didn't (defaults to `good`)
    is_objection: bool = False
    objection_label: str = ""
    coach_note: str = ""              # shown in the transcript, not spoken

    def line(self, landed: bool) -> str:
        if landed or not self.poor:
            return self.good
        return self.poor


# --------------------------------------------------------------------------
# Opening lines by difficulty
# --------------------------------------------------------------------------

PICKUP = {
    "normal": "Mike Delaney.",
    "hostile": "Yeah? Who's this.",
    "apathetic": "This is Mike.",
    "timepoor": "Delaney. Make it quick, I'm out on site.",
}

REACT_OPENER = {
    "normal": (
        "Alright. Thirty seconds. Go ahead.",
        "Hang on, who is this? Are you selling me something?",
    ),
    "hostile": (
        "You've got one sentence, and then I'm hanging up.",
        "I don't take cold calls. What do you want?",
    ),
    "apathetic": (
        "Sure, I guess. Go ahead.",
        "Look, I'm not really in the market for anything.",
    ),
    "timepoor": (
        "Fine, go, but I've got about a minute before I lose you.",
        "I'm walking a job right now. What is this about?",
    ),
}

# --------------------------------------------------------------------------
# Objection pools -- phrasing varies run to run so you can't memorise a script
# --------------------------------------------------------------------------

OBJ_PAPER = [
    "Let me save you some time. We've run jobs on paper for thirty years and it works "
    "fine. I've got binders in my truck that have never once crashed on me.",
    "I'll stop you there. Thirty years we've done this with paper and a pencil, and we "
    "still hand jobs over on time. Why would I change that now?",
    "Honestly? We've been doing it the same way since before you were born and it works. "
    "Paper doesn't need a password.",
]

OBJ_BURNED = [
    "Here's my problem though. We bought a system four, five years back. Paid for it, sat "
    "through the training, and nobody in the field touched it. Guys went straight back to "
    "paper. I'm not doing that again.",
    "We already tried this. Bought a platform, big rollout, and six months later everyone "
    "was back on paper and we were still paying for it. Burned me pretty good.",
    "Last time we brought software in, it was a disaster. The office loved it, the field "
    "wouldn't touch it, and I'm the one who had to run the job in the middle of that.",
]

OBJ_CLOSE = [
    "Alright, look. Just send me an email and I'll take a look when I get a minute.",
    "Do me a favour and just email me something. I don't have time for another call.",
    "Send me an email. If it's worth it I'll get back to you.",
]

OBJ_CLOSE_ALT = [
    "Before we go further, what does something like this run? Give me a number.",
    "Hold on. How much is this going to cost me?",
]

# What the PM gives up once you've actually asked him something real.
PAIN_REVEAL = [
    "Honestly? Closeout. Every single job, the last three weeks is me and a coordinator "
    "digging through paper trying to build the binder. And change orders -- half of them "
    "get built before anybody signs off, and then I'm the one eating it.",
    "If I'm being straight with you, it's the change orders and the drawings. We had a "
    "crew on the Dundas job frame off a set the architect had already revised. Cost us the "
    "better part of a week to tear it out and redo it.",
    "The daily logs, mostly. My super writes them from memory at six o'clock at night, and "
    "then when the owner comes back with a delay claim, I've got nothing solid to point at.",
]


# Short punches for --drill only. Full-call PAIN_REVEAL stays long.
# Mapped 1:1 to the v1 implication bank "when he says" column.
PAIN_DRILL_CUES = [
    "We had a crew on the Dundas job frame off a set the architect had already revised. Cost us the better part of a week.",
    "Closeout. Every job, the last three weeks is me and a coordinator digging through paper trying to build the binder.",
    "Half the change orders get built before anybody signs off, and then I'm the one eating it.",
    "The daily logs, mostly. My super writes them from memory at six o'clock at night, and when the owner comes back with a delay claim I've got nothing solid.",
    "RFIs sit in a truck for two weeks and the crew's either standing around or building ahead off a guess.",
]


def pain_drill_cues(n: int, rng: random.Random) -> List[str]:
    """n cues, shuffled then cycled, so ten shots are not the same sentence ten times."""
    order = list(PAIN_DRILL_CUES)
    rng.shuffle(order)
    return [order[i % len(order)] for i in range(n)]


def build_script(difficulty: str, rng: random.Random) -> List[Stage]:
    """Assemble the PM's side of the call for one session."""
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"unknown difficulty {difficulty!r}")

    good_open, poor_open = REACT_OPENER[difficulty]
    close_pool = OBJ_CLOSE + (OBJ_CLOSE_ALT if rng.random() < 0.35 else [])

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


# Said when you go silent long enough that a real prospect would prompt you.
FREEZE_PROMPTS = [
    "Hello? You still there?",
    "You there?",
    "I've got about ten seconds here, buddy.",
]

SIGN_OFF = {
    True: "Alright. Talk then.",
    False: "Yeah. Good luck.",
}
