"""RIQ persona briefs, distilled from the interview playbooks.

Sources (user-provided PDFs):
  - RIQ ("RISK") Cold Calling Framework          -> the call shape + philosophy
  - The Signal-Based Selling Playbook            -> trigger taxonomy / plays
  - AudienceView Mock Cold Call Playbook (Oct 2026) -> personas A-F, V1 + V2,
    objection grid, listening discipline, technicality trap
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RiqBrief:
    id: str                       # "A1" .. "F2" (V1/V2)
    persona: str                  # buyer first name
    title: str
    company_desc: str             # their world, in their words' vocabulary
    external_trigger: str         # R: irrefutable industry fact
    internal_signal: str          # I: observable signal at THEIR org
    challenge_hint: str           # the shape of a strong Q against their status quo
    status_quo: str               # buyer's private answer to a good Q
    pains: List[str]              # what they admit when probed properly
    objections: List[str]         # first-person brush-offs (playbook grid + scripts)
    pickup: str                   # opening words when the phone is answered
    play: str                     # taxonomy / play from the persona table
    riq_terms: Dict[str, List[str]] = field(default_factory=dict)   # R/I regex banks
    source: str = ""              # playbook section, for maintenance

    @property
    def label(self) -> str:
        return f"{self.id}: {self.persona}, {self.title}"


BRIEFS: List[RiqBrief] = [
    RiqBrief(
        id="A1",
        persona="Susie",
        title="marketing director",
        company_desc=("a mid-size professional theatre — a 13,000+ patron list, "
                      "productions running most weekends of the year, and a "
                      "marketing team of two"),
        external_trigger=("season subscriptions are turning into memberships and "
                          "flex passes sector-wide — the season ticket is becoming "
                          "a membership"),
        internal_signal=("productions most weekends of the year, a marketing team "
                         "of two, and a 13,000+ patron list"),
        challenge_hint=("connect their subscription shift to her two-person list "
                        "grind — 'how are you getting show-specific emails out "
                        "without spending half your week exporting and cleaning "
                        "lists?'"),
        status_quo=("we're all set on email, honestly. We use Constant Contact. "
                    "It does what we need it to do — I pull buyers out of the "
                    "ticketing system, clean it, dedupe by hand, upload, pray it "
                    "doesn't land in spam… basically a full day per campaign."),
        pains=[
            "a manual export, clean, dedupe and upload grind for every single "
            "campaign",
            "no way to tell which campaigns actually drove ticket sales",
            "the membership campaign and the socials keep going quiet",
        ],
        objections=[
            "we're all set on email, we use Constant Contact",
            "we just renewed our ticketing contract in the spring — it's a "
            "three-year contract",
            "send me something in writing first… I'm not booking a meeting off "
            "one cold call",
            "the last vendor swore his thing 'integrated' — it was a CSV export "
            "and a 40-minute webinar",
        ],
        pickup=("Okay, thirty seconds. But make it fast, we're two weeks out "
                "from on-sale."),
        play="Operational / The Infrastructure Pitch",
        riq_terms={
            "R": [r"memberships?\b|flex passes?\b|subscriptions?\b"],
            "I": [r"team of two|13,?000|most weekends|patron list|constant contact"],
        },
        source="AV §5 + Round-1 debrief (Noell's Susie)",
    ),
    RiqBrief(
        id="A2",
        persona="Susie",
        title="marketing director",
        company_desc=("a mid-size professional theatre that just announced a "
                      "second stage opening next season"),
        external_trigger=("venues across the sector are adding second and "
                          "black-box stages for year-round revenue"),
        internal_signal="her theatre just announced a second stage opening next season",
        challenge_hint=("connect the second-stage announcement to the workload — "
                        "'how are you going to market two venues' worth of shows "
                        "with the same team?'"),
        status_quo="we haven't figured out marketing two venues yet.",
        pains=[
            "two calendars of shows to sell",
            "the same team of two doing it all",
        ],
        objections=[
            "we're not a big venue, this is built for bigger orgs",
            "we'd need to ask the GM.",
        ],
        pickup="Go ahead.",
        play="Operational / The Infrastructure Pitch",
        riq_terms={
            "R": [r"second stage|black-?box|year-round"],
            "I": [r"second stage|announcement|next season"],
        },
        source="AV §5 V2",
    ),
    RiqBrief(
        id="B1",
        persona="Megan",
        title="box office manager",
        company_desc=("a university tickets office covering everything from main "
                      "stage through club events across many departments"),
        external_trigger=("campus ticketing is squeezed from both sides — students "
                          "expect mobile and cashless while finance wants cleaner "
                          "revenue data"),
        internal_signal=("her office covers main stage through club events across "
                         "many departments"),
        challenge_hint=("make the hand-checking cost concrete — 'what does a "
                        "waved-through student discount cost you at reconciliation?'"),
        status_quo=("we check student IDs at will-call, by hand; it's slow but it "
                    "works."),
        pains=[
            "discount integrity enforced by hand at will-call",
            "reconciliation and cashless handling eat staff hours",
        ],
        objections=[
            "we already have a system that does tickets. I don't see us switching.",
        ],
        pickup="I can give you a couple of minutes before my next thing.",
        play="Hiring / The Scaling Pitch",
        riq_terms={
            "R": [r"cashless|mobile|revenue data|finance"],
            "I": [r"departments|will-?call|student discount|club events"],
        },
        source="AV §6",
    ),
    RiqBrief(
        id="B2",
        persona="Megan",
        title="box office manager",
        company_desc=("a university box office where nearly the whole student crew "
                      "turns over every fall"),
        external_trigger=("campus box offices backfill nearly the whole student "
                          "crew every fall"),
        internal_signal="her season opens with a mostly new student staff",
        challenge_hint=("make training the bottleneck — 'what happens to opening "
                        "weekend if your new crew is still learning the system on "
                        "day one?'"),
        status_quo="training is exactly what's killing me right now.",
        pains=[
            "a brand-new crew has to sell tickets, comps and discounts correctly "
            "by opening weekend",
        ],
        objections=[
            "we've always trained them ourselves",
            "call me after the season starts.",
        ],
        pickup="It's my whole world right now, everyone's back on campus.",
        play="Hiring / The Scaling Pitch",
        riq_terms={
            "R": [r"turn ?over|student crew|backfill|every fall"],
            "I": [r"new staff|opening weekend|training|august"],
        },
        source="AV §6 V2",
    ),
    RiqBrief(
        id="C1",
        persona="Donnie",
        title="festival producer",
        company_desc=("a festival production company in the middle of its "
                      "early-bird push with significant media budget behind it"),
        external_trigger=("festivals are spending more on ads than ever and flying "
                          "blind on attribution"),
        internal_signal=("his early-bird push just went live; significant media "
                         "budget"),
        challenge_hint=("make the attribution blindness cost — 'if I asked which "
                        "channel sold your last hundred early-bird tickets, could "
                        "anyone actually tell you?'"),
        status_quo=("the agency sends a report, but nobody has ever shown me a "
                    "ticket attached to an ad; I'm not paying for another "
                    "dashboard — we have three."),
        pains=[
            "attribution blindness across email, SMS and social",
            "presale data sitting in scattered lists",
        ],
        objections=[
            "I'm not paying for another dashboard",
            "we think it's email.",
        ],
        pickup="Thirty seconds, go.",
        play="Operational / The Scaling Pitch",
        riq_terms={
            "R": [r"attribution|channel|ad spend|email,? sms"],
            "I": [r"early-?bird|presale|lineup|on-?sale"],
        },
        source="AV §7",
    ),
    RiqBrief(
        id="C2",
        persona="Donnie",
        title="festival producer",
        company_desc=("a festival that just added a second weekend and new grounds "
                      "to meet demand"),
        external_trigger=("festivals are adding second weekends and new grounds to "
                          "meet post-2024 demand"),
        internal_signal="he just added a second weekend",
        challenge_hint=("make the two-spreadsheet blind spot cost — 'how do you "
                        "know when the first weekend is pacing slow enough to pivot "
                        "ad spend to the second?'"),
        status_quo="we're looking at it in two spreadsheets right now, honestly.",
        pains=[
            "no pace-of-sale visibility across two capacity buckets",
        ],
        objections=[
            "I've got site meetings all day",
            "our agency handles the reporting.",
        ],
        pickup="Make it good, I've got site meetings all day.",
        play="Operational / The Scaling Pitch",
        riq_terms={
            "R": [r"second weekend|new grounds|post-?2024"],
            "I": [r"two spreadsheets|doubled|weekend"],
        },
        source="AV §7 V2",
    ),
    RiqBrief(
        id="D1",
        persona="Elena",
        title="membership & visitor engagement director",
        company_desc="a science museum with a traveling exhibit opening this fall",
        external_trigger=("museums everywhere are turning one-time visitors into "
                          "members and pass holders — recurring revenue instead of "
                          "door traffic"),
        internal_signal="her traveling exhibit opens this fall",
        challenge_hint=("make the Monday volunteer sync the risk — 'what happens "
                        "to your membership numbers the Monday your volunteer "
                        "isn't here?'"),
        status_quo=("a volunteer reconciles the two systems every Monday; the "
                    "member database is our donor CRM — nobody is replacing it."),
        pains=[
            "hand-syncing the ticketing system and the member database",
            "renewal season dependency for revenue",
            "leadership wants recurring revenue she cannot yet produce",
        ],
        objections=[
            "the member database is our donor CRM, nobody is replacing it",
            "we already pay for systems that do this.",
        ],
        pickup="I've got a minute before we open at ten.",
        play="Financial / The Deep Pockets Play",
        riq_terms={
            "R": [r"members?\b|pass ?holders?|recurring revenue"],
            "I": [r"traveling exhibit|monday|volunteer|ticketing and the member"],
        },
        source="AV §8",
    ),
    RiqBrief(
        id="D2",
        persona="Elena",
        title="membership & visitor engagement director",
        company_desc="a science museum that just won a city cultural grant",
        external_trigger=("municipal and state cultural grant cycles just landed "
                          "with spending deadlines attached"),
        internal_signal="her museum won a city cultural grant this cycle",
        challenge_hint=("never ask the amount — ask about the deadline: 'when does "
                        "the spending window close, and what has to be in the plan "
                        "before it does?'"),
        status_quo="we're supposed to have that plan written already, honestly.",
        pains=[
            "deploying grant money into member acquisition before the spending "
            "window closes",
        ],
        objections=[
            "we have to report on every grant dollar",
            "finance owns the grant.",
        ],
        pickup="Sure, I've got a couple of minutes.",
        play="Financial / The Deep Pockets Play",
        riq_terms={
            "R": [r"grant season|grant dollars|spending deadline"],
            "I": [r"city cultural grant|this cycle|plan"],
        },
        source="AV §8 V2",
    ),
    RiqBrief(
        id="E1",
        persona="Marissa",
        title="county fair & year-round event grounds manager",
        company_desc="a county fairground running a year-round event calendar",
        external_trigger=("fairs are turning into year-round venues and fairgoers "
                          "expect cashless at the gate and the midway"),
        internal_signal="her concert announcements just went up",
        challenge_hint=("make the hand-sync cost concrete — 'what happens when the "
                        "website calendar and the ticketing system disagree on a "
                        "sold-out night?'"),
        status_quo=("my office manager re-enters the concert sales into the "
                    "website calendar by hand — fourteen concerts plus rodeo "
                    "nights."),
        pains=[
            "website and ticketing kept in sync by hand",
            "seasonal staff double-entering everything",
        ],
        objections=[
            "call me after the fair (a booked callback — take the date)",
            "the fair board weighs in on spend.",
        ],
        pickup="Sure, but we are deep in planning, so fast.",
        play="Product launch + fraud / Scaling Pitch",
        riq_terms={
            "R": [r"year-round|cashless|concert series"],
            "I": [r"concert announcements|fourteen concerts|rodeo|website calendar"],
        },
        source="AV §9",
    ),
    RiqBrief(
        id="E2",
        persona="Marissa",
        title="county fair & year-round event grounds manager",
        company_desc="a county fairground with grandstand headliners",
        external_trigger=("grandstand headliners drive the biggest on-sale spikes "
                          "and bots hit them first"),
        internal_signal="she just announced a major headliner",
        challenge_hint=("name the on-sale spike and make 'sell and hope' cost — "
                        "and if she asks how blocking works, do not bluff the "
                        "mechanics (technicality trap: she cools on bluffing)"),
        status_quo="we just sell and hope, honestly.",
        pains=[
            "real fans striking out in the on-sale",
            "window staff drowning in complaints after every spike",
        ],
        objections=[
            "we're mid-planning, no time",
            "how would you even stop bots?",
        ],
        pickup="Fast, we're mid-planning.",
        play="Product launch + fraud / Scaling Pitch",
        riq_terms={
            "R": [r"bots?|resellers?|on-?sale spike|headliners?"],
            "I": [r"headliner|announcement|on-?sale date"],
        },
        source="AV §9 V2",
    ),
    RiqBrief(
        id="F1",
        persona="Diane",
        title="box office manager",
        company_desc=("a 1,800-seat performing arts venue with a part-time window "
                      "crew"),
        external_trigger=("ticket buyers are fee-shy — 42% say fees decide whether "
                          "they come back"),
        internal_signal=("she's the one at the window when a patron blows up over "
                         "a service charge she didn't set"),
        challenge_hint=("put a number on the window abuse — 'what does it cost you "
                        "when a patron takes the fee out on your staff?'"),
        status_quo=("every week my kids at the window take the abuse, and the fee "
                    "is not even ours; the GM says the contract is the contract."),
        pains=[
            "absorbing patron anger over fees she does not control",
            "part-time window staff",
            "nightly reconciliation",
        ],
        objections=[
            "I do not control the ticketing system",
            "the GM says the contract is the contract.",
        ],
        pickup="Sure, it's quiet until the afternoon rush anyway.",
        play="Hiring / The Fresh Eyes Pitch",
        riq_terms={
            "R": [r"fees?\b|service charge|42\s*%|fee-?shy"],
            "I": [r"window|patron|abuse|the fee is not even ours"],
        },
        source="AV §10",
    ),
    RiqBrief(
        id="F2",
        persona="Diane",
        title="box office manager",
        company_desc="a 1,800-seat performing arts venue with a new executive director",
        external_trigger=("new EDs and GMs audit their ticketing stack in their "
                          "first 90 days"),
        internal_signal="her venue just hired a new executive director",
        challenge_hint=("get her wishlist into the audit — 'if the new executive "
                        "director asked you for one change, what would you tell "
                        "them?'"),
        status_quo="nobody's asked me what I'd change, honestly.",
        pains=[
            "getting the window wishlist into the audit list before it's written",
        ],
        objections=[
            "that's above my head",
            "we just renewed our system.",
        ],
        pickup="Sure, I can talk.",
        play="Hiring / The Fresh Eyes Pitch",
        riq_terms={
            "R": [r"first 90 days|audit list|new (?:executive director|gm)s?"],
            "I": [r"new executive director|announcement|wishlist"],
        },
        source="AV §10 V2",
    ),
]


def get_brief(brief_id: str) -> RiqBrief:
    for b in BRIEFS:
        if b.id == brief_id:
            return b
    raise KeyError(brief_id)


def list_briefs() -> List[str]:
    return [b.id for b in BRIEFS]
