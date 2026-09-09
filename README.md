# Mock Cold Call Trainer — Procore SDR Role-Play

A live cold-call drill for the Skillset round on Friday. You speak into the mic, a
skeptical Senior Project Manager talks back out loud, and at the end you get graded
against Procore's five published role-play criteria plus the five failure modes from
your own job-hunt diagnosis. Every session is recorded.

Built to run the **Wed 19th** drill from the Mock Call Roleplay Playbook: *"Run three
full mock calls out loud. Do them badly — the point is reps, not polish. Note every
place you froze or filled silence."* This program notes those places for you, with
numbers.

---

## Quick start

Double-click **`run.bat`**, or from a terminal:

```powershell
cd C:\Users\Jason\Documents\Interview\mock_call_trainer
.\.venv\Scripts\python.exe mock_call.py
```

Wear headphones so the mic doesn't record the PM's voice back into your turn.

First run downloads the transcription model (~75 MB) once, then works offline.

---

## What happens on a call

1. It calibrates your background noise, then you press ENTER to dial.
2. **Mike Delaney**, Sr. Project Manager at a GTA general contractor, picks up.
   He's influential, skeptical, burned by tech before, and runs every job on paper.
3. You talk. A beep means it's your turn. Stop talking for ~3 seconds and your turn ends.
4. He works through the real objection sequence: **paper for 30 years → burned by tech,
   nobody used it → brush-off at the close.** Phrasing changes every run so you can't
   memorise a script.
5. He gets warmer if you handle him well and colder if you don't. Acknowledge his
   objection and he opens up about closeout and change orders. Pitch at him and he shuts down.
6. Your objective: book the AE intro with **two specific times**. He only says yes if you
   actually offer two.

If you go silent too long he'll say *"Hello? You still there?"* — same as a real prospect.

---

## Difficulty modes

| Command | Persona |
| --- | --- |
| `mock_call.py` | **normal** — skeptical but will engage |
| `mock_call.py -d hostile` | tries to end the call in ten seconds, talks fast |
| `mock_call.py -d apathetic` | "we're fine, paper works" |
| `mock_call.py -d timepoor` | genuinely interested but standing on a job site |

---

## Pain-reveal drill

Skips the full call. Mike names a pain, you price it, ten times or three minutes.
Grades only: did a cost question come out, and how fast.

```powershell
.\.venv\Scripts\python.exe mock_call.py --drill
.\.venv\Scripts\python.exe mock_call.py --drill --text
.\.venv\Scripts\python.exe mock_call.py --drill --reps 10 --minutes 3
```

Double-click `drill.bat`. Headphones on. One ENTER starts the whole set.

FAST ≤ 3.0s, OK ≤ 6.0s, SLOW = question but late, MISS = no cost question.
Target: 10/10 FAST. Writes `sessions/<timestamp>-drill/` and `sessions/drill_history.csv`.
Does not write a full-call scorecard and does not touch `sessions/history.csv`.
Drill silence is capped at 1.5s even if you pass a larger `--silence`.

---

## Paraphrase drill

Fixes the opposite problem from every other mode. The others reward getting the right
line out fast, which is how twelve reps produced a **forty-word opener recited verbatim
in five of them**. Fast recall of a fixed sentence is exactly what "you sounded scripted"
means.

Here the idea has to survive but the wording can't repeat. Each shot is checked twice:

1. **Did the meaning survive?** Same concept checks the grader already uses, per beat.
   Reword freely, but an opener still has to admit the interruption, ask for the time and
   give him an out; the close still needs two named times; the cost beat still needs a
   consequence question.
2. **Is the wording new?** Rejected if it shares **5+ content words in a row** with
   anything already said, or **70% content-word overlap**.

```powershell
.\.venv\Scripts\python.exe mock_call.py --paraphrase                    # opener, 10 shots
.\.venv\Scripts\python.exe mock_call.py --paraphrase --beat hook
.\.venv\Scripts\python.exe mock_call.py --paraphrase --beat all --reps 14
.\.venv\Scripts\python.exe mock_call.py --paraphrase --list-beats
```

Double-click `paraphrase.bat`. Headphones on. One ENTER starts the whole set.

Verdicts: **FRESH** (banked, can't be reused), **RECITED** (shows the exact span you
reused and which prior attempt it collided with), **LOST IDEA** (new words, but the
meaning didn't survive), **FROZE**.

**The ban list is seeded from your own history.** On first run it harvests what you
actually said in every recorded rep, mapped to the matching beat, so your memorised
version is rejected on attempt one instead of sailing through. It then persists in
`sessions/paraphrase_bank.json` and grows every session, which is what makes it bite:
by the twentieth attempt the easy wordings are gone and the idea has to stand on its own.

Rejected attempts are banked too. A phrasing you reached for is one you'd reach for
again.

| Beat | What has to survive the rewording |
| --- | --- |
| `opener` | Admits the cold call, asks for the time, gives him an out, ends on a question |
| `hook` | Peer reference plus a concrete problem, no capability talk |
| `obj_paper` | Acknowledges first, uses his language, ends on a question |
| `discovery` | A construction noun plus a real probe, still no features |
| `cost` | A consequence question: money, schedule, or who absorbs it |
| `obj_burned` | Acknowledges, then gets curious about what failed without defending software |
| `close` | Two specific times |

Tune the strictness with `--max-run` and `--jaccard` if it's rejecting things that are
genuinely different. Start over with `--reset-bank`, or re-harvest from your reps with
`--reseed`.

---

## What it grades

**Procore's five published criteria** (their exact scoring sheet):

| Criterion | How it's measured |
| --- | --- |
| Relevant industry language | Distinct high-value construction terms you used (RFI, submittal, change order, superseded set, closeout, daily log, holdback, look-ahead…). Tells you which ones you missed. |
| Ask targeted questions | Real questions about *his* jobs. "Is this Mike?" and "can I take thirty seconds?" don't count. |
| Uncover the pain | Whether he actually named a headache in his own words, and whether you asked an implication question that made it cost something. |
| Book a follow-up | Whether you named **two specific times**, and whether he accepted. |
| Handle objections | Per objection: did you acknowledge before answering, and did you end on a question? |

**Your measured failure modes** (from the audio, not guessed — 7 metrics, driven by the five diagnosed leaks):

| Metric | What it catches |
| --- | --- |
| Time to first word on the opener | **Freezing at hello.** Target under 1.5s. |
| Pause before answering an objection | Under 0.6s means you cut in and talked past it. Over 3s means you froze. |
| Acknowledged first (%) | Talking past objections. Target 100%. |
| Questions before your first capability claim | **Pitching before pain.** Zero is a hard fail. |
| Filler-word rate per 100 words | Filling silence out of nerves. Target under 3. |
| Longest single turn | Monologuing. Flags anything over 130 words. |
| Banned SaaS filler | Flags every use of visibility / efficiency / streamline / solution / pain points / synergy / game-changer, with the turn number. |

It finishes with a verdict — *would Reena believe you could take a real call next week?* —
and the three things to fix on your next rep.

---

## Outputs

Each session writes to `sessions/<timestamp>/`:

- **`session.wav`** — the full call, both sides, so you can listen back
- **`report.md`** — scorecard, leak metrics, and the annotated transcript with your
  timings on every turn

Plus one row per rep in **`sessions/history.csv`**, so you can watch the numbers move
across reps the same way you'd track a funnel. For a per-session progression of the
headline metrics (criteria/5, opener latency, ack %, filler rate, longest turn,
banned words, freezes), run `python trend.py`.

---

## Options

| Flag | Purpose |
| --- | --- |
| `-d, --difficulty` | `normal`, `hostile`, `apathetic`, `timepoor` |
| `--text` | Type your answers instead of speaking. Useful for a silent rehearsal or to sanity-check grading. |
| `--model` | `tiny.en`, `base.en` (default), `small.en`. Use `small.en` if it's mishearing jargon. |
| `--fast` | Quicker transcription, slightly less accurate. |
| `--silence` | Seconds of silence that end your turn (default `3.0`). Raise it if you're practising long deliberate pauses. |
| `--device` | Mic index, if the default is wrong. |
| `--list-devices` | Show available microphones. |
| `--seed` | Fix the objection phrasing for a repeatable run. |
| `--drill` | Pain-reveal only: 10 shots or 3 minutes, cost question + speed. |
| `--paraphrase` | Same idea, new wording every time. Reused phrasing is rejected. |
| `--beat` | Paraphrase target: `opener` (default), `hook`, `obj_paper`, `discovery`, `cost`, `obj_burned`, `close`, `all`, or a comma-separated list. |
| `--list-beats` | Show the paraphrase beats and exit. |
| `--max-run` | Identical content words in a row that count as reciting (default 5). |
| `--jaccard` | Content-word overlap that counts as reciting (default 0.70). |
| `--reseed` | Re-harvest the paraphrase ban list from past session reports. |
| `--reset-bank` | Wipe the paraphrase ban list and start over. |
| `--reps` | Shot count (default 10). Used by `--drill` and `--paraphrase`. |
| `--minutes` | Time budget in minutes (default 3). Used by `--drill` and `--paraphrase`. |

---

## Suggested drill (the Wed 19th plan)

```powershell
.\.venv\Scripts\python.exe mock_call.py -d normal      # rep 1 - just get through it
.\.venv\Scripts\python.exe mock_call.py -d apathetic   # rep 2 - he won't give you pain
.\.venv\Scripts\python.exe mock_call.py -d hostile     # rep 3 - ten seconds to survive
```

Then open `sessions/history.csv` and look at three numbers: time to first word,
acknowledged-first percentage, and whether you offered two times. Those are the three
that decide Friday.

---

## Self-test

Verifies the whole speech path (Windows TTS → transcription → grader) without a human:

```powershell
.\.venv\Scripts\python.exe tests\test_pipeline.py
```

`tests/good_call.txt` and `tests/weak_call.txt` are reference transcripts — piping them
into `--text` mode should score 5/5 and 0/5 respectively:

```powershell
Get-Content .\tests\good_call.txt | .\.venv\Scripts\python.exe mock_call.py --text
```

---

## Files

| File | Purpose |
| --- | --- |
| `mock_call.py` | Call loop, mic capture and timing, transcription, session recording |
| `persona.py` | Mike Delaney's dialogue, the objection pools, difficulty settings |
| `grader.py` | Rubric scoring, vocabulary and filler banks, report rendering |
| `drill.py` | Pain-reveal drill loop (cost question + speed only) |
| `paraphrase.py` | Paraphrase drill: beats, novelty scoring, the persisted ban list |
| `regrade.py` | Re-score saved sessions with the current grader |
| `trend.py` | Cross-session progress view of history.csv |
| `run.bat` | Double-click launcher |
| `drill.bat` | Double-click pain-reveal drill |
| `paraphrase.bat` | Double-click paraphrase drill |
| `sessions/` | Recordings, reports, history.csv, drill_history.csv, paraphrase_bank.json |

Set `MOCKCALL_SESSIONS` to redirect all output somewhere else. The CLI tests use it so
they can't append fake rows to your real history or drop junk folders next to your reps.

No API keys and no internet needed after the first model download. Grading is fully
deterministic, so the same call always scores the same and reps are comparable.
