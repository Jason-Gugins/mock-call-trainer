"""Per-company profiles for the mock cold call trainer.

Everything company/domain-specific lives in a Profile; the engine modules read
from the Profile passed in instead of hardcoding. `generic_saas` is the default;
`procore` (construction) is preserved as an example profile.

Add a company by building a Profile and registering it in PROFILE. The regex
fields are plain strings matched via re.search against normalized lowercase.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class Stage:
    id: str
    expects: str
    good: str
    poor: str = ""
    is_objection: bool = False
    objection_label: str = ""
    coach_note: str = ""

    def line(self, landed: bool) -> str:
        if landed or not self.poor:
            return self.good
        return self.poor


@dataclass
class Beat:
    id: str
    label: str
    cue: str                       # what the buyer says first (empty = cold)
    instruction: str
    concepts: Dict[str, str] = field(default_factory=dict)
    min_concepts: int = 2
    require_question: bool = False
    require_ack: bool = False
    require_implication: bool = False
    min_time_offers: int = 0
    forbid_capability: bool = False
    seed_turn: Optional[int] = None

    def check_idea(self, text: str) -> Tuple[bool, List[str]]:
        """Did the meaning survive? Returns (ok, list of what's missing)."""
        import grader  # local import avoids a profiles<->grader cycle

        missing: List[str] = []
        hit = [name for name, pat in self.concepts.items()
               if re.search(pat, (text or "").lower())]
        if len(hit) < self.min_concepts:
            need = self.min_concepts - len(hit)
            absent = [n for n in self.concepts if n not in hit]
            missing.append(f"need {need} more of: {', '.join(absent)}")
        if self.require_question and not grader.has_question(text):
            missing.append("no question")
        if self.require_ack and not grader.is_acknowledged(text):
            missing.append("did not acknowledge first")
        if self.require_implication and not grader.has_implication_question(text):
            missing.append("no cost/consequence question")
        if self.min_time_offers:
            offers = grader.find_time_offers(text)
            if len(offers) < self.min_time_offers:
                missing.append(f"{len(offers)} specific times, need {self.min_time_offers}")
        if self.forbid_capability and grader.mentions_capability(text):
            missing.append("pitched a capability")
        return (not missing), missing


@dataclass
class Profile:
    name: str
    display: str
    company: str
    buyer_name: str
    buyer_title: str
    objective: str
    difficulty_rates: Dict[str, int]
    pickup: Dict[str, str]
    react_opener: Dict[str, Tuple[str, str]]
    objection_pools: Dict[str, List[str]]
    pain_reveal: List[str]
    pain_drill_cues: List[str]
    high_value_terms: Dict[str, str]
    contextual_terms: Dict[str, str]
    whisper_primer: str
    freeze_prompts: List[str]
    sign_off: Dict[bool, str]
    beats: Dict[str, Beat] = field(default_factory=dict)
    beat_order: List[str] = field(default_factory=list)
    star_stories: List[str] = field(default_factory=list)
    hook_markers: List[str] = field(default_factory=list)
    c1_priority: List[str] = field(default_factory=list)
    build_script: Callable = None     # bound to build_script() by register()


def build_script(difficulty: str, rng: random.Random, profile: Profile) -> List[Stage]:
    """Neutral 9-stage SaaS cold call. Objection/pain wording comes from profile."""
    if difficulty not in profile.pickup:
        raise ValueError(f"unknown difficulty {difficulty!r}")
    good_open, poor_open = profile.react_opener[difficulty]
    close_pool = list(profile.objection_pools.get("close", []) or
                      profile.objection_pools.get("status_quo", []))
    if "close_alt" in profile.objection_pools and rng.random() < 0.35:
        close_pool += profile.objection_pools["close_alt"]
    pain = list(profile.pain_reveal)
    return [
        Stage("pickup",
              "Your two-sentence permissive-interruption opener, said cold.",
              profile.pickup[difficulty],
              coach_note="Freezing here is your #1 documented leak. Opener must be automatic."),
        Stage("react_opener",
              "Your R+I hook: external fact + internal signal, peer-referenced. Then the long pause.",
              good_open, poor_open,
              coach_note="Landed = you asked permission. Poor = you launched in without it."),
        Stage("obj_status",
              "Acknowledge -> Reframe -> Redirect, ending on a question. Do not argue.",
              rng.choice(list(profile.objection_pools["status_quo"])),
              is_objection=True, objection_label="status quo / it works fine",
              coach_note="Pause ~1s before you answer. Acknowledge the kernel of truth first."),
        Stage("react_handle_1",
              "Two or three targeted discovery questions in his language. No features yet.",
              "Yeah, alright. That does happen. We've got a team that feels it every week.",
              "You're not really answering me. This sounds like every other software call I get.",
              coach_note="He opens up only if you acknowledged him instead of pitching."),
        Stage("pain_reveal",
              "Follow the thread. One implication question -- what is it costing him?",
              rng.choice(pain),
              "I mean, it's fine. We manage. Everybody's got headaches.",
              coach_note="This is the pain you were sent to uncover. Do not pitch over it."),
        Stage("obj_burned",
              "Get curious about WHAT failed. Don't defend software. Don't bash the vendor.",
              rng.choice(list(profile.objection_pools["burned"])),
              is_objection=True, objection_label="burned by tech / nobody used it",
              coach_note="The heart of the brief. Ask whether it was the tool or the rollout."),
        Stage("react_handle_2",
              "Value in their terms -- usability + a phased start. Then move to the close.",
              "That's fair. It was the rollout, mostly. The team never had a reason to open it.",
              "See, this is what I mean. You're already selling me the thing.",
              coach_note="Landed = you got curious. Poor = you defended the software."),
        Stage("obj_close",
              "Close for the next call with TWO specific times.",
              rng.choice(close_pool),
              is_objection=True, objection_label="brush-off at the close",
              coach_note="Two named times, or he walks. This is the objective of the call."),
        Stage("resolution",
              "Confirm the next step, set a one-line agenda, ask what he wants covered.",
              "Fine. Thursday at seven works, before the day gets busy. Send the invite and "
              "tell your person I want to know how it handles that.",
              "Yeah, just send me the email. I've got to go.",
              coach_note="He only says yes if you offered two specific times."),
    ]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROFILE: Dict[str, Profile] = {}
DEFAULT_PROFILE = "generic_saas"


def get_profile(name: str) -> Profile:
    if name not in PROFILE:
        raise KeyError(name)
    return PROFILE[name]


def list_profiles() -> List[str]:
    return sorted(PROFILE)


def register(profile: Profile) -> Profile:
    profile.build_script = build_script
    PROFILE[profile.name] = profile
    return profile


# ---------------------------------------------------------------------------
# generic_saas beats (no construction references)
# ---------------------------------------------------------------------------

def _generic_beats() -> Dict[str, Beat]:
    return {
        "opener": Beat(
            id="opener", label="Permissive-interruption opener",
            cue="Alex Moore.",
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
            min_concepts=2, require_question=True, seed_turn=1,
        ),
        "hook": Beat(
            id="hook", label="Reason for the call (peer reference + real problem)",
            cue="Alright. Thirty seconds. Go ahead.",
            instruction="Why you called: peers like him, and a concrete problem. No features.",
            concepts={
                "peer reference": r"\bother\b|\bteams?\b|\bcompanies\b|\bleaders?\b|\bmanagers?\b"
                                  r"|\bpeers?\b|\bgcs?\b|\bvps?\b|\bdirectors?\b|\bshops?\b",
                "concrete problem": r"\bpipeline|\bleads?\b|\bchurn\b|\bhandoff\b|\bhand[- ]?off"
                                    r"|\bforecast|\brevenue|\bfollow ?up|\bdata quality|\bcrm\b"
                                    r"|\bconversion|\bquota|\bdemo\b|\bdark\b",
            },
            min_concepts=2, forbid_capability=True, seed_turn=2,
        ),
        "obj_status": Beat(
            id="obj_status", label="Objection: 'it works fine / we're fine'",
            cue="We've run our process this way for years and it works fine. I'm not looking to change anything.",
            instruction="Acknowledge, reframe, redirect. End on a question. Do not argue.",
            concepts={
                "concedes the point": r"\bfair\b|\bworks?\b|\bnot wrong\b|\bright\b|\bbelieve\b"
                                      r"|\bagree\b|\byears?\b|\bhear you\b"
                                      r"|\bwon'?t (argue|pretend)\b|\bno argument\b|\brespect\b",
                "his language": r"\bcrm|\bteam\b|\bleads?\b|\bpipeline|\bforecast"
                                r"|\bprocess\b|\bspreadsheet|\bdata\b|\bflow\b",
            },
            min_concepts=2, require_question=True, require_ack=True,
            forbid_capability=True, seed_turn=3,
        ),
        "discovery": Beat(
            id="discovery", label="Targeted discovery question in his language",
            cue="Yeah, alright. That does happen. We lost a big deal last quarter to a follow-up gap.",
            instruction="Ask about his process, using domain nouns. Still no features.",
            concepts={
                "domain artifact": r"\bcrm|\bpipeline|\bleads?|\bforecast|\bhandoff|\bhand[- ]?off"
                                   r"|\breport|\bdata\b|\bprocess|\bsequence|\bcadence",
                "probe": r"\bhow\b|\bwhat\b|\bwhen\b|\bwhere\b|\bwho\b|\bwalk me\b|\btell me\b"
                         r"|\btalk me\b|\bhelp me understand\b",
            },
            min_concepts=2, require_question=True, forbid_capability=True, seed_turn=4,
        ),
        "cost": Beat(
            id="cost", label="Implication question (what the pain costs him)",
            cue="We lost a big deal last quarter because the follow-up fell through. Cost us the quarter.",
            instruction="Make it cost something. Money, schedule, or who absorbs it.",
            concepts={}, min_concepts=0, require_question=True,
            require_implication=True, forbid_capability=True, seed_turn=5,
        ),
        "obj_burned": Beat(
            id="obj_burned", label="Objection: bought software before, nobody used it",
            cue="We bought a system four years back. Paid for it, sat through the training, "
                "and nobody in the field touched it. I'm not doing that again.",
            instruction="Get curious about what actually failed. Don't defend software.",
            concepts={
                "concedes the point": r"\bfair\b|\bhear you\b|\bbelieve\b|\bdon'?t blame\b"
                                      r"|\bhappens\b|\bcommon\b|\bnot wrong\b|\bwon'?t (argue|pretend)\b"
                                      r"|\bmakes sense\b|\bi bet\b|\bunderstand\b",
                "probes the failure": r"\bwhat happened\b|\bwhich part\b|\bwas it\b|\bteam\b"
                                      r"|\brollout\b|\broll ?out\b|\btraining\b"
                                      r"|\badopt|\buse ?d? it\b|\bwhy\b|\bwhere did\b|\bwho (set|ran|led)\b"
                                      r"|\bhow was it\b|\bwhat did\b",
            },
            min_concepts=2, require_question=True, require_ack=True,
            forbid_capability=True, seed_turn=6,
        ),
        "close": Beat(
            id="close", label="Close for the follow-up with two specific times",
            cue="Just send me an email and I'll take a look when I get a minute.",
            instruction="Two named times. Not 'sometime next week'.",
            concepts={}, min_concepts=0, min_time_offers=2, seed_turn=8,
        ),
    }


GENERIC_BEAT_ORDER = ["opener", "hook", "obj_status", "discovery", "cost",
                      "obj_burned", "close"]

GENERIC_STAR_STORIES = [
    "Tim Hortons drive-thru (metrics + pressure)",
    "Self-directed outbound project (initiative)",
    "A failure and what you learned from it",
]


# ---------------------------------------------------------------------------
# generic_saas profile (the default)
# ---------------------------------------------------------------------------

register(Profile(
    name="generic_saas", display="Generic SaaS BDR", company="a mid-size SaaS company",
    buyer_name="Alex", buyer_title="VP of Operations",
    objective="Book a follow-up call with a real decision-maker, with two specific times.",
    difficulty_rates={"normal": 0, "hostile": 2, "apathetic": -1, "timepoor": 3},
    pickup={
        "normal": "Alex Moore.",
        "hostile": "Yeah? Who's this.",
        "apathetic": "This is Alex.",
        "timepoor": "Alex. Make it quick, I'm in back-to-backs.",
    },
    react_opener={
        "normal": ("Alright. Thirty seconds, go ahead.",
                   "Hang on, who is this? Are you selling me something?"),
        "hostile": ("You've got one sentence, then I'm hanging up.",
                    "I don't take cold calls. What do you want?"),
        "apathetic": ("Sure, I guess. Go ahead.",
                      "Look, I'm not really in the market for anything."),
        "timepoor": ("Fine, go, but I've got about a minute before I lose you.",
                     "I'm between meetings. What is this about?"),
    },
    objection_pools={
        "status_quo": [
            "We've run things this way for years and it works fine. I'm not looking to change anything.",
            "Honestly, we've managed without it until now, and we're still hitting our numbers.",
            "We've been doing it the same way for years and it works. It doesn't need a password.",
        ],
        "burned": [
            "Here's my problem though. We bought a system four, five years back. Paid for it, sat through "
            "the training, and nobody used it. Guys went straight back to how we always did it. Not doing that again.",
            "We already tried this. Bought a platform, big rollout, and six months later everyone was back "
            "on the old way and we were still paying for it. Burned me pretty good.",
            "Last time we brought a tool in, it was a disaster. The office loved it, nobody in the day-to-day "
            "touched it, and I was the one left holding it.",
        ],
        "close": [
            "Alright, look. Just send me an email and I'll take a look when I get a minute.",
            "Do me a favour and just email me something. I don't have time for another call.",
            "Send me an email. If it's worth it I'll get back to you.",
        ],
        "close_alt": [
            "Before we go further, what does something like this run? Give me a number.",
            "Hold on. How much is this going to cost me?",
        ],
    },
    pain_reveal=[
        "Honestly? Follow-up. Deals stall because we lose track of who we've talked to and what we "
        "promised, and it's costing us revenue we should have closed.",
        "If I'm being straight with you, it's the handoff. Marketing generates leads and they die in the "
        "gap before sales ever picks them up. Leads we paid for, sitting dark.",
        "Data quality, mostly. Our CRM is a mess, nothing's consistent, and nobody trusts the numbers "
        "when it's time to forecast.",
    ],
    pain_drill_cues=[
        "Deals stall because we lose track of who we've talked to and what we promised. What does that cost you?",
        "Marketing generates leads and they die in the gap before sales picks them up. Where does that leave your pipeline?",
        "Our CRM is a mess and nobody trusts the numbers at forecast. Who eats that?",
        "Leads sit dark for two weeks before anyone calls. How far behind does that push you?",
    ],
    high_value_terms={
        "pipeline": r"\bpipeline\b",
        "crm": r"\bcrm\b",
        "conversion / kpi": r"\bconversion\b|\bkpis?\b",
        "churn": r"\bchurn(?:ing|ed)?\b",
        "lead / mql / sql": r"\bleads?\b|\bmqls?\b|\bsqls?\b",
        "rep / quota / target": r"\breps?\b|\bquota\b|\btargets?\b",
        "discovery / demo": r"\bdiscovery\b|\bdemo\b",
        "onboarding / adoption": r"\bonboard|\badoption\b",
        "forecast / revenue": r"\bforecast\b|\brevenue\b",
        "follow-up / nurture": r"\bfollow[- ]?up\b|\bnurtur\b",
        "sequence / cadence": r"\bsequence\b|\bcadence\b",
        "data quality / hygiene": r"\bdata quality\b|\bhygien\b",
    },
    contextual_terms={
        "decision-maker": r"\bdecision[- ]?maker\b|\bbuyer\b",
        "leader/manager": r"\bmanager\b|\bvp\b|\bdirector\b",
        "handoff": r"\bhandoff\b|\bhand[- ]?off\b",
        "meeting booked": r"\b(book|schedule|set)[a-z ]{0,20}(call|meeting|intro|deck)\b",
    },
    whisper_primer=(
        "A cold call with a decision-maker at a SaaS company. Terms used: pipeline, CRM, "
        "conversion, churn, lead, MQL, SQL, rep, quota, target, discovery call, demo, "
        "onboarding, adoption, forecast, revenue, follow-up, nurture, sequence, cadence, "
        "data quality, handoff."
    ),
    freeze_prompts=["Hello? You still there?", "You there?",
                    "I've got about ten seconds here."],
    sign_off={True: "Alright. Talk then.", False: "Yeah. Good luck."},
    beats=_generic_beats(),
    beat_order=list(GENERIC_BEAT_ORDER),
    star_stories=list(GENERIC_STAR_STORIES),
    hook_markers=["pipeline", "crm", "churn", "churning", "forecast", "forecasts",
                  "leads", "lead", "handoff", "hand-off", "revenue", "conversion",
                  "quota", "demo", "dark", "follow up", "follow-up", "nurture"],
    c1_priority=["pipeline", "crm", "conversion / kpi", "churn",
                 "lead / mql / sql", "forecast / revenue"],
))


# ---------------------------------------------------------------------------
# boostsecurity profile (example of a real target employer)
# ---------------------------------------------------------------------------

# AI-native ASPM / DevSecOps platform (Montreal): secure the CI/CD software
# supply chain - developer endpoint, dependencies/supply chain, and code.
# Buyer: an AppSec / security engineering lead. Real objections: scanner
# fatigue (noise/false positives), developer adoption, supply-chain risk.
# Authored 2026-09 with the company's own language; verify pains/vocab against
# the current homepage and any briefing before a live round.

register(Profile(
    name="boostsecurity", display="BoostSecurity (AI-native ASPM)",
    company="BoostSecurity",
    buyer_name="Priya", buyer_title="AppSec Team Lead at a fast-growing SaaS company",
    objective="Book a technical walkthrough with the BoostSecurity AE, two specific times.",
    difficulty_rates={"normal": 0, "hostile": 2, "apathetic": -1, "timepoor": 3},
    pickup={
        "normal": "Priya Sharma.",
        "hostile": "Yeah? Who's this.",
        "apathetic": "This is Priya.",
        "timepoor": "Priya. Make it quick, I'm in the middle of a pentest review.",
    },
    react_opener={
        "normal": ("Alright. Thirty seconds, go ahead.",
                   "Hang on, who is this? Are you selling me another security tool?"),
        "hostile": ("You've got one sentence, then I'm hanging up.",
                    "I don't take cold calls about security. What do you want?"),
        "apathetic": ("Sure, I guess. Go ahead.",
                      "Look, I'm not really in the market for anything."),
        "timepoor": ("Fine, go, but I've got about a minute before a report lands.",
                     "I'm mid-incident. What is this about?"),
    },
    objection_pools={
        "status_quo": [
            "We already run a scanner and a pentest program. Our security is covered.",
            "Developers have enough alerts already. I'm not adding another tool they'll ignore.",
            "We've managed our risk this long without a platform. Why change now?",
        ],
        "burned": [
            "Here's my problem though. We bought a security platform four years back. The "
            "devs never looked at a single finding - it just added noise. I'm not doing that again.",
            "We already tried an ASPM tool. It was a dashboard nobody opened, and we were "
            "still paying for it. Burned me pretty good.",
            "Every security vendor says their tool won't slow shipping, and every one has. "
            "I've been burned enough.",
        ],
        "close": [
            "Alright, look. Just send me an email and I'll take a look when I get a minute.",
            "Do me a favour and just email me something. I don't have time for another call.",
            "Send me an email. If it's worth it I'll get back to you.",
        ],
        "close_alt": [
            "Before we go further, what does something like this run? Give me a number.",
            "Hold on. How much is this going to cost me?",
        ],
    },
    pain_reveal=[
        "Honestly? Noise. We run three scanners and most of the findings are false positives, "
        "so nobody trusts the queue and real risk slips through to production.",
        "It's adoption. Security keeps buying tools and developers keep ignoring them, and I'm "
        "the one explaining why our posture looks bad at audit.",
        "The supply chain. A malicious dependency or a compromised build gets in before we even "
        "know it, and one bad package can take the company down.",
    ],
    pain_drill_cues=[
        "Most of our scanner findings are false positives, so developers ignore the queue and real risk slips through. What does that cost you?",
        "Security bought two platforms last year and the devs never opened them. Where does that leave your AppSec backlog?",
        "A malicious dependency can get into a build before anyone notices. Who absorbs that if it ships?",
        "We have thousands of findings and no way to tell what's actually reachable. How do you prioritize?",
    ],
    high_value_terms={
        "vulnerability / CVE": r"\b(cve|vulnerabilit(?:y|ies))\b",
        "SAST / DAST": r"\bsast\b|\bdast\b|\bscanner\b|\bscan(?:ning)?\b",
        "reachability": r"\breachab\w*\b",
        "ASPM / posture": r"\baspm\b|\bposture\b",
        "supply chain / SBOM": r"\bsupply chain\b|\bsbom\b",
        "CI/CD / pipeline": r"\bci/?cd\b|\bpipeline\b|\bbuild\b",
        "remediation / fix": r"\bremediat\w*\b|\bauto-?fix\b|\bfix\b",
        "alert / finding / noise": r"\balert(?:s)?\b|\bfinding(?:s)?\b|\bnoise\b",
        "exposure / misconfig": r"\bexpos(?:e|ed|ure)\b|\bmisconfigur\w*\b",
        "dependency": r"\bdependenc(?:y|ies)\b|\bpackage(?:s)?\b",
        "threat / exploit": r"\bthreat(?:s)?\b|\bexploit\b|\bliving off the pipeline\b",
        "DevSecOps / AppSec": r"\bdevsecops\b|\bappsec\b|\bapplication security\b",
    },
    contextual_terms={
        "developer / engineering": r"\bdev(?:s|eloper)?s?\b|\bengineer(?:ing|s)?\b|\bplatform team\b",
        "CI vendors": r"\bgithub\b|\bgitlab\b|\bazure\b|\bcircleci\b",
        "security team": r"\bsecurity team\b|\bappsec\b|\bpentest\b|\breview\b|\baudit\b",
        "sprint / repo": r"\bsprint\b|\brepo(?:s)?\b|\bcommit\b|\bpr\b|\bpull request\b",
    },
    whisper_primer=(
        "A cold call with an AppSec team lead at a SaaS company about securing the "
        "software supply chain. Terms used: vulnerability, CVE, SAST, DAST, scanner, "
        "reachability, ASPM, posture, supply chain, SBOM, CI/CD, pipeline, build, "
        "remediation, auto-fix, alert, finding, noise, exposure, misconfiguration, "
        "dependency, package, threat, exploit, DevSecOps, AppSec, Application Security."
    ),
    freeze_prompts=["Hello? You still there?", "You there?",
                    "I've got about ten seconds here."],
    sign_off={True: "Alright. Talk then.", False: "Yeah. Good luck."},
    beats=_generic_beats(),
    beat_order=list(GENERIC_BEAT_ORDER),
    star_stories=list(GENERIC_STAR_STORIES),
    hook_markers=["appsec", "secu", "scanner", "pipeline", "supply chain", "cve",
                  "vulnerab", "reachab", "noise", "finding", "sast", "dast",
                  "copilot", "agent", "code"],
    c1_priority=["vulnerability / CVE", "supply chain / SBOM", "reachability",
                 "SAST / DAST", "ASPM / posture", "CI/CD / pipeline"],
))


# ---------------------------------------------------------------------------
# mentimeter profile (example of a live target employer)
# ---------------------------------------------------------------------------

# Enterprise audience-engagement / interactive-presentations SaaS (used by a
# majority of Fortune 500; L&D platform + leadership comms + meetings). Buyer:
# a Learning & Development / People leader. Real pains: training impact is a
# black box, all-hands are one-way, engagement is scattered so it can't be
# measured. Authored 2026-09 from public materials; verify before a live round.

register(Profile(
    name="mentimeter", display="Mentimeter (audience engagement)",
    company="Mentimeter",
    buyer_name="Jordan", buyer_title="Head of Learning & Development at a mid-size company",
    objective="Book a walkthrough with the Mentimeter AE, two specific times.",
    difficulty_rates={"normal": 0, "hostile": 2, "apathetic": -1, "timepoor": 3},
    pickup={
        "normal": "Jordan.",
        "hostile": "Yeah? Who's this.",
        "apathetic": "This is Jordan.",
        "timepoor": "Jordan. Make it quick, I'm between trainings.",
    },
    react_opener={
        "normal": ("Alright. Thirty seconds, go ahead.",
                   "Hang on, who is this? Are you selling me software?"),
        "hostile": ("You've got one sentence, then I'm hanging up.",
                    "I don't take cold calls. What do you want?"),
        "apathetic": ("Sure, I guess. Go ahead.",
                      "Look, we're fine with how we run training today."),
        "timepoor": ("Fine, go, but I've got about a minute before a session.",
                     "I'm about to run a training. What is this about?"),
    },
    objection_pools={
        "status_quo": [
            "Our people already use the free version when they need engagement. Why would we buy a central license?",
            "We run training with our LMS and slide decks and it works fine. I'm not looking to change it.",
            "Engagement on our team is fine. We're not in the market for another meeting tool.",
        ],
        "burned": [
            "Here's my problem though. We bought an engagement platform four years back. It was dead "
            "after onboarding - nobody standardized on it. I'm not doing that again.",
            "We rolled out a meeting-tool platform before, everyone used it once, and it fell off. "
            "Burned me pretty good.",
            "Every L&D vendor says their tool will finally make training stick, and none of them have. "
            "I've heard it before.",
        ],
        "close": [
            "Alright, look. Just send me an email and I'll take a look when I get a minute.",
            "Do me a favour and just email me something. I don't have time for another call.",
            "Send me an email. If it's worth it I'll get back to you.",
        ],
        "close_alt": [
            "Before we go further, what does something like this run? Give me a number.",
            "Hold on. How much is this going to cost me?",
        ],
    },
    pain_reveal=[
        "Honestly? Training never sticks. We run the sessions, completion gets checked, but nobody "
        "knows if it actually changed behavior - impact is a black box we can't report to leadership.",
        "It's the all-hands and policy comms. It's one-way, people check out, and we can't tell if "
        "anything actually landed - so there's always a compliance risk nobody can see.",
        "Engagement is scattered. Every team runs its own thing, so we can't measure adoption or "
        "show value when it's time to defend our budget.",
    ],
    pain_drill_cues=[
        "Our trainings get completion checkboxes but we can't show behavior change or impact. What does that cost you?",
        "All-hands is a one-way stream and we can't tell if anything landed. Where does that leave your leadership comms?",
        "Every team runs engagement differently, so we can't measure adoption. Who owns that at report time?",
        "Policy training gets the checkbox but not the understanding. How far does that gap take your compliance risk?",
    ],
    high_value_terms={
        "engagement": r"\bengag(?:e|ed|ement)\b",
        "training / L&D": r"\btraining(?:s)?\b|\bld\b|\blearning\b|\bdevelopment program\b",
        "impact / behavior": r"\bimpact\b|\bbehavio(?:u)?r\b|\boutcome(?:s)?\b",
        "adoption": r"\badopt\w*\b|\brollout\b",
        "participation": r"\bparticipation\b|\binteractive\b|\bparticipation rate\b",
        "poll / quiz / feedback": r"\bpoll(?:s)?\b|\bquiz(?:zes)?\b|\bfeedback\b|\bsurvey(?:s)?\b",
        "all-hands / comms": r"\ball[- ]?hands\b|\bcommunication(?:s)?\b|\bcomms\b|\bbriefing\b",
        "measurement / KPI": r"\bmeasure\w*\b|\bkpis?\b|\bmetrics\b|\binsights\b",
        "onboarding / policy": r"\bonboard\w*\b|\bpolicy\b|\bcompliance\b|\bcertification\b",
        "audience / presenter": r"\baudience\b|\bpresenter(?:s)?\b|\bmeeting leader\b|\bworkshop",
        "scale / rollout": r"\bscal\w*\b|\bstandardiz\w*\b|\broll(?:-| )?out",
    },
    contextual_terms={
        "teams / people": r"\bteam(?:s)?\b|\bpeople\b|\bemployee(?:s)?\b|\bfolks\b",
        "meeting / session": r"\bmeeting(?:s)?\b|\bsession(?:s)?\b|\bworkshop(?:s)?\b",
        "format tools": r"\bslide(?:s)?\b|\bdeck\b|\bweb(?:inar)?\b|\blms\b",
        "leaders": r"\bleader(?:s)?\b|\bexec(?:s)?\b|\bmanagement\b|\bstakeholder(?:s)?\b",
    },
    whisper_primer=(
        "A cold call with a learning and development leader at a company about "
        "audience engagement for trainings, meetings, and all-hands. Terms used: "
        "engagement, training, learning, L&D, impact, behavior, adoption, "
        "participation, polls, quizzes, feedback, all-hands, communication, "
        "measurement, KPI, insights, onboarding, policy, compliance, audience, "
        "presenter, workshop, scale, standardized rollout."
    ),
    freeze_prompts=["Hello? You still there?", "You there?",
                    "I've got about ten seconds here."],
    sign_off={True: "Alright. Talk then.", False: "Yeah. Good luck."},
    beats=_generic_beats(),
    beat_order=list(GENERIC_BEAT_ORDER),
    star_stories=list(GENERIC_STAR_STORIES),
    hook_markers=["training", "learning", "engagement", "all hands", "all-hands",
                  "meeting", "workshop", "onboarding", "policy", "compliance",
                  "adoption", "impact", "feedback", "poll"],
    c1_priority=["engagement", "training / L&D", "impact / behavior", "adoption",
                 "measurement / KPI", "all-hands / comms"],
))


# ---------------------------------------------------------------------------
# procore profile (example — construction). Beats are shared with the existing
# paraphrase module so old behaviour is preserved.
# ---------------------------------------------------------------------------

_procore = Profile(
    name="procore", display="Procore (construction SaaS)", company="Delaney Construction Group",
    buyer_name="Mike Delaney", buyer_title="Senior Project Manager at a GTA general contractor",
    objective="Book an intro call between him and a Procore AE, with two specific times.",
    difficulty_rates={"normal": 0, "hostile": 2, "apathetic": -1, "timepoor": 3},
    pickup={"normal": "Mike Delaney.", "hostile": "Yeah? Who's this.",
            "apathetic": "This is Mike.", "timepoor": "Delaney. Make it quick, I'm out on site."},
    react_opener={
        "normal": ("Alright. Thirty seconds. Go ahead.",
                   "Hang on, who is this? Are you selling me something?"),
        "hostile": ("You've got one sentence, and then I'm hanging up.",
                    "I don't take cold calls. What do you want?"),
        "apathetic": ("Sure, I guess. Go ahead.",
                      "Look, I'm not really in the market for anything."),
        "timepoor": ("Fine, go, but I've got about a minute before I lose you.",
                     "I'm walking a job right now. What is this about?"),
    },
    objection_pools={
        "status_quo": [
            "Let me save you some time. We've run jobs on paper for thirty years and it works "
            "fine. I've got binders in my truck that have never once crashed on me.",
            "I'll stop you there. Thirty years we've done this with paper and a pencil, and we "
            "still hand jobs over on time. Why would I change that now?",
            "Honestly? We've been doing it the same way since before you were born and it works. "
            "Paper doesn't need a password.",
        ],
        "burned": [
            "Here's my problem though. We bought a system four, five years back. Paid for it, sat "
            "through the training, and nobody in the field touched it. Guys went straight back to "
            "paper. I'm not doing that again.",
            "We already tried this. Bought a platform, big rollout, and six months later everyone "
            "was back on paper and we were still paying for it. Burned me pretty good.",
            "Last time we brought software in, it was a disaster. The office loved it, the field "
            "wouldn't touch it, and I'm the one who had to run the job in the middle of that.",
        ],
        "close": [
            "Alright, look. Just send me an email and I'll take a look when I get a minute.",
            "Do me a favour and just email me something. I don't have time for another call.",
            "Send me an email. If it's worth it I'll get back to you.",
        ],
        "close_alt": [
            "Before we go further, what does something like this run? Give me a number.",
            "Hold on. How much is this going to cost me?",
        ],
    },
    pain_reveal=[
        "Honestly? Closeout. Every single job, the last three weeks is me and a coordinator "
        "digging through paper trying to build the binder. And change orders -- half of them "
        "get built before anybody signs off, and then I'm the one eating it.",
        "If I'm being straight with you, it's the change orders and the drawings. We had a "
        "crew on the Dundas job frame off a set the architect had already revised. Cost us the "
        "better part of a week to tear it out and redo it.",
        "The daily logs, mostly. My super writes them from memory at six o'clock at night, and "
        "then when the owner comes back with a delay claim, I've got nothing solid to point at.",
    ],
    pain_drill_cues=[
        "We had a crew on the Dundas job frame off a set the architect had already revised. Cost us the better part of a week.",
        "Closeout. Every job, the last three weeks is me and a coordinator digging through paper trying to build the binder.",
        "Half the change orders get built before anybody signs off, and then I'm the one eating it.",
        "The daily logs, mostly. My super writes them from memory at six o'clock at night, and when the owner comes back with a delay claim I've got nothing solid.",
        "RFIs sit in a truck for two weeks and the crew's either standing around or building ahead off a guess.",
    ],
    high_value_terms={
        "RFI": r"\brfi(?:s)?\b",
        "submittal": r"\bsubmittal(?:s)?\b",
        "change order": r"\bchange order(?:s)?\b|\bchange directive(?:s)?\b",
        "drawing revision / superseded set": r"\bsupersede(?:d)?\b|\brevision(?:s)?\b|\b(?:current|old|latest|new) set\b|\bre-?issued\b",
        "as-built": r"\bas-?built(?:s)?\b",
        "daily log": r"\bdaily (?:log|logs|report|reports)\b",
        "punch list": r"\bpunch ?list(?:s)?\b|\bdeficiency list\b",
        "closeout": r"\bclose-?out\b",
        "look-ahead schedule": r"\blook-?ahead\b",
        "holdback": r"\bholdback(?:s)?\b",
        "lien": r"\blien(?:s)?\b",
        "T&M ticket": r"\bt ?& ?m\b|\btime and materials\b",
        "schedule of values": r"\bschedule of values\b",
        "progress billing / pay app": r"\bprogress billing\b|\bpay app(?:lication)?(?:s)?\b|\bprogress claim\b",
        "scope gap": r"\bscope gap(?:s)?\b",
        "rework": r"\brework\b|\btear ?out\b",
        "safety observation": r"\bsafety observation(?:s)?\b",
        "shop drawing": r"\bshop drawing(?:s)?\b",
        "prime contract / subcontract": r"\bprime contract\b|\bsubcontract(?:s)?\b",
    },
    contextual_terms={
        "superintendent": r"\bsuperintendent(?:s)?\b|\bsuper\b",
        "foreman": r"\bforeman\b|\bforemen\b",
        "crew": r"\bcrew(?:s)?\b",
        "subs / trades": r"\bsub(?:s)?\b|\btrade(?:s)?\b|\bsubcontractor(?:s)?\b",
        "jobsite": r"\bjob ?site(?:s)?\b|\bon site\b|\bjob walk\b",
        "general contractor": r"\bgeneral contractor(?:s)?\b|\bgc(?:s)?\b",
        "architect": r"\barchitect\b",
        "drawings / specs": r"\bdrawing(?:s)?\b|\bspec(?:s)?\b|\bprint(?:s)?\b",
        "schedule": r"\bschedule\b",
    },
    whisper_primer=(
        "A cold call with a construction project manager at a general contractor. "
        "Terms used: RFI, submittal, change order, drawing revision, superseded set, "
        "as-built, daily log, punch list, closeout, holdback, look-ahead schedule, "
        "schedule of values, progress billing, T&M ticket, rework, scope gap, "
        "superintendent, foreman, general contractor, Procore."
    ),
    freeze_prompts=["Hello? You still there?", "You there?",
                    "I've got about ten seconds here, buddy."],
    sign_off={True: "Alright. Talk then.", False: "Yeah. Good luck."},
    hook_markers=["talking to", "talking with", "been speaking", "other", "pms",
                  "p m s", "contractors", "gcs", "construction act", "payment",
                  "labour", "labor", "retire", "rework", "tariff", "market",
                  "shortage", "prompt payment", "adjudication", "holdback", "peers"],
    c1_priority=["RFI", "submittal", "change order", "closeout",
                 "daily log", "drawing revision / superseded set"],
)
register(_procore)


# NOTE: procore's paraphrase beats (construction) live in paraphrase.py and are
# attached there at import time so profiles can import standalone without a
# circular dependency.

