"""Same-brief A/B replay diff from the per-rep transcript.json files.

Each rep now writes a machine-readable transcript.json next to report.md (see
llm_call._persist / mock_call._persist). This tool reads two of those and shows
what actually changed between reps: the criteria table with an up/down arrow
per criterion (STRONG > PASS > FAIL), the shared leak deltas, and the
beat-by-beat replay with divergent turns flagged.

    python ab_diff.py sessions/llm/2026-01-01_090000 sessions/llm/2026-01-02_090000
    python ab_diff.py <dirA> <dirB> --json     # machine output instead

--json emits exactly: {"a": meta, "b": meta, "criteria": [{"key", "a", "b",
"change"}...], "leaks": [{"key", "a", "b", "changed"}...], "turns": [{"i",
"buyer", "a", "b", "divergent"}...]}. meta is {"session", "kind", "brief",
"difficulty", "model", "fallback", "summary"}; summary is the count of
criteria at PASS or better. change is "^" (better), "v" (worse), "=" (same)
or "?" (unknown/missing level). A turn is `divergent` when either side is
missing it or the said-text lengths differ by more than 40%.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

STRONG, PASS, FAIL = "STRONG", "PASS", "FAIL"
_RANK = {STRONG: 3, PASS: 2, FAIL: 1}
TRANSCRIPT = "transcript.json"
DIVERGENT = "<< divergent >>"
BANNER = "=" * 72


class AbDiffError(Exception):
    """An actionable load failure; main turns it into exit code 2."""


def _load(d: Path) -> dict:
    if not d.is_dir():
        raise AbDiffError(
            f"ab_diff: no directory at {d}\n"
            f"       pass the session folder that holds {TRANSCRIPT} "
            f"(e.g. sessions/llm/<timestamp>)")
    path = d / TRANSCRIPT
    if not path.exists():
        raise AbDiffError(
            f"ab_diff: {d} has no {TRANSCRIPT}\n"
            f"       reps recorded before transcripts existed don't carry one; "
            f"re-run the rep to generate it")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AbDiffError(f"ab_diff: {path} is not valid JSON: {exc}")


# --------------------------------------------------------------------------
# Diff pieces (pure; also unit-tested directly)
# --------------------------------------------------------------------------

def meta(t: dict) -> dict:
    """The header block for one side, including the PASS-or-better count."""
    criteria = t.get("criteria", {})
    summary = sum(1 for lv in criteria.values() if lv in (PASS, STRONG))
    return {"session": t.get("session", ""), "kind": t.get("kind", ""),
            "brief": t.get("brief", ""), "difficulty": t.get("difficulty", ""),
            "model": t.get("model", ""), "fallback": bool(t.get("fallback")),
            "summary": summary}


def _arrow(a_level, b_level) -> str:
    ra, rb = _RANK.get(a_level), _RANK.get(b_level)
    if ra is None or rb is None:
        return "?"
    return "^" if rb > ra else ("v" if rb < ra else "=")


def diff_criteria(a: dict, b: dict) -> List[dict]:
    """Rows sorted by key; change arrow by STRONG > PASS > FAIL."""
    rows = []
    for k in sorted(set(a.get("criteria", {})) | set(b.get("criteria", {}))):
        la, lb = a.get("criteria", {}).get(k), b.get("criteria", {}).get(k)
        rows.append({"key": k, "a": la, "b": lb, "change": _arrow(la, lb)})
    return rows


def diff_leaks(a: dict, b: dict) -> List[dict]:
    """String deltas for keys present on BOTH sides; one-sided keys are noise."""
    rows = []
    for k in sorted(set(a.get("leaks", {})) & set(b.get("leaks", {}))):
        va, vb = a["leaks"][k], b["leaks"][k]
        rows.append({"key": k, "a": va, "b": vb, "changed": va != vb})
    return rows


def _beats(t: dict) -> Dict[int, Dict[str, str]]:
    idx: Dict[int, Dict[str, str]] = {}
    for e in t.get("turns", []):
        idx.setdefault(int(e.get("i", 0)), {})[e.get("who", "")] = \
            e.get("text", "")
    return idx


def _turn_count(t: dict) -> int:
    return len({e.get("i") for e in t.get("turns", []) if e.get("who") == "you"})


def diff_turns(a: dict, b: dict) -> List[dict]:
    """Beat-by-beat rows for i in 1..max turn count. The buyer prompt is A's;
    a turn diverges when either side is missing it or the said-text lengths
    differ by more than 40%."""
    beats_a, beats_b = _beats(a), _beats(b)
    rows = []
    for i in range(1, max(_turn_count(a), _turn_count(b)) + 1):
        buyer = beats_a.get(i, {}).get("buyer", "")
        a_you = beats_a.get(i, {}).get("you")
        b_you = beats_b.get(i, {}).get("you")
        if a_you is None or b_you is None:
            divergent = True
        else:
            la, lb = len(a_you), len(b_you)
            divergent = abs(la - lb) / max(la, lb, 1) > 0.4
        rows.append({"i": i, "buyer": buyer, "a": a_you, "b": b_you,
                     "divergent": divergent})
    return rows


def build_json(a: dict, b: dict) -> dict:
    return {"a": meta(a), "b": meta(b), "criteria": diff_criteria(a, b),
            "leaks": diff_leaks(a, b), "turns": diff_turns(a, b)}


# --------------------------------------------------------------------------
# Pretty print
# --------------------------------------------------------------------------

def _side_block(label: str, path, t: dict) -> List[str]:
    m = meta(t)
    n = len(t.get("criteria", {})) or 1
    return [f"  {label}:  {path}",
            f"        session {m['session']}   kind {m['kind']}",
            f"        brief {m['brief']}   {m['difficulty']}   "
            f"model {m['model'] or '-'}   "
            f"fallback {'Y' if m['fallback'] else 'N'}",
            f"        {m['summary']}/{n} criteria at PASS or better"]


def _lvl(v) -> str:
    return v if isinstance(v, str) and v else "?"


def render(a: dict, b: dict, path_a, path_b) -> str:
    lines = [BANNER, "  A/B REPLAY DIFF", BANNER]
    lines += _side_block("A", path_a, a)
    lines += _side_block("B", path_b, b)

    crit = diff_criteria(a, b)
    w_key = max([len(r["key"]) for r in crit] + [len("CRITERION")])
    w_lvl = max([len(_lvl(r["a"])) for r in crit]
                + [len(_lvl(r["b"])) for r in crit] + [len(STRONG)])
    lines += ["", f"  {'CRITERION':<{w_key}}  {'A':>{w_lvl}}  {'B':>{w_lvl}}  "
                  f"CHANGE"]
    for r in crit:
        lines.append(f"  {r['key']:<{w_key}}  {_lvl(r['a']):>{w_lvl}}  "
                     f"{_lvl(r['b']):>{w_lvl}}  {r['change']}")

    leaks = diff_leaks(a, b)
    if leaks:
        w_lk = max(len(r["key"]) for r in leaks)
        w_va = max(len(str(r["a"])) for r in leaks)
        lines += ["", "  LEAKS (shared keys)"]
        for r in leaks:
            lines.append(f"  {r['key']:<{w_lk}}  {str(r['a']):>{w_va}}  "
                         f"{r['b']}  {'changed' if r['changed'] else 'same'}")

    lines += ["", "  TURN BY TURN"]
    for r in diff_turns(a, b):
        lines.append(f"  --- turn {r['i']} ---")
        lines.append(f"  buyer: {r['buyer'] or '<missing>'}")
        lines.append(f"  A you: {r['a'] if r['a'] is not None else '<missing>'}")
        lines.append(f"  B you: {r['b'] if r['b'] is not None else '<missing>'}")
        if r["divergent"]:
            lines.append(f"  {DIVERGENT}")
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="A/B replay diff between two per-rep transcript.json files")
    ap.add_argument("dir_a", help="session dir A (must contain transcript.json)")
    ap.add_argument("dir_b", help="session dir B (must contain transcript.json)")
    ap.add_argument("--json", action="store_true",
                    help="emit the whole diff as one JSON object")
    args = ap.parse_args(argv)
    try:
        a = _load(Path(args.dir_a))
        b = _load(Path(args.dir_b))
    except AbDiffError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        # ASCII-escaped so it pipes cleanly through any console encoding
        # (transcript text carries whatever the rep actually said).
        print(json.dumps(build_json(a, b), indent=1))
    else:
        print(render(a, b, args.dir_a, args.dir_b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
