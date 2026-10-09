"""Shared harness for golden grading-corpus tests.

A corpus file is the candidate's 9 turns, one per line, in script order.
simulate() replays them through the real builder + grader with the same
landing semantics run_call uses (pain_revealed = turn 4 asked a question;
meeting_booked = turn 8 offered two times).

The profile is passed by name (the file prefix before _good/_weak).
persona.build_script dispatches per profile: procore gets its construction
builder (stage 3 = obj_paper, "paper for 30 years"); every other profile
gets the generic builder (stage 3 = obj_status).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grader as G
import persona
import profiles

DATA = Path(__file__).resolve().parent / "data"


def load_lines(name: str) -> list:
    raw = (DATA / name).read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in raw if ln.strip() and not ln.startswith("#")]


def simulate(profile_name: str, lines: list) -> G.Report:
    profile = profiles.get_profile(profile_name)
    stages = persona.build_script("normal", random.Random(0), profile)
    # run_call evaluates pain_revealed BEFORE the pain_reveal turn executes, so
    # this is turn 4's landing (react_handle_1) -- intentionally lines[3], not
    # lines[4]. Verified against mock_call.run_call during planning.
    pain_revealed = G.has_question(lines[3])
    turns, meeting_booked = [], False
    for i, (st, said) in enumerate(zip(stages, lines), start=1):
        if st.id == "obj_close":
            meeting_booked = len(G.find_time_offers(said)) >= 2
        turns.append(G.Turn(index=i, stage_id=st.id, expects=st.expects,
                            pm_line=st.line(True), text=said,
                            onset_latency=0.8,        # healthy on every clock
                            duration=12.0, internal_gaps=[],
                            is_objection=st.is_objection,
                            objection_label=st.objection_label, froze=False))
    return G.grade(turns, "normal", pain_revealed, meeting_booked, profile=profile)
