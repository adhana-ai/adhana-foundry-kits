"""Check one close cycle's drafted journal entry and account reconciliation against its recurring
template's basis document: load both, one model call, check the citations, done.

This is the whole AI layer of the kit, deliberately short — the same split data-reconcile's
reconcile.py, docs-comply's comply.py and docs-verify's verify.py all make: the model does one job,
and this file is small enough that you can see exactly which one.

⚠︎ THIS IS A TWO-SOURCE CHECK, NOT A ONE-DOCUMENT-AGAINST-A-FIXED-RULEBOOK CHECK — same shape as
data-reconcile, for the same reason:

  · docs-comply runs a FIXED rulebook -> many documents. Every document is checked against the
    same rules.
  · This kit runs one close cycle -> its OWN recurring template's basis document, resolved per
    cycle by rje_id. Two close cycles from two templates are checked against two different basis
    documents, and a drafted entry can state a basis or an account its own template's document
    never mentions -- the unverifiable verdict this kit exists to get right.

⚑ THIS KIT NEVER POSTS, APPROVES OR CLEARS ANYTHING. `check()` below returns a verdict per check
and nothing else -- there is no function anywhere in this file, or in src/app.py, that writes a
journal entry, marks a reconciling item cleared, or records reviewer sign-off. Every entry and
every clearance still requires a named preparer and a named reviewer, outside this kit, exactly as
the basis document's own segregation-of-duties paragraph states. The verdict this file returns is a
DRAFT for that human chain to act on -- see the module docstring in src/prompt.py for where that
boundary is worded to the model itself.

The cost of the two-source shape is stated on the page rather than hidden: nothing here is cached
across close cycles from the same template, so re-checking five cycles against one template sends
that template's basis text five times. See Cost.cost_drivers once a run has priced it.
"""
import os

from . import adapters, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASIS = os.path.join(HERE, "data", "basis")
CYCLES = os.path.join(HERE, "data", "close_cycles.jsonl")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚑ THE OUTPUT CEILING, NAMED ONCE — same discipline as every sibling kit's MAX_TOKENS. A full
# reply is four checks, each with a verdict, a citation and two values: short by the standard of
# docs-comply's 41-rule reply, so this starts well under it. A guess, not a measurement, until a
# real run's finish_reason says otherwise.
MAX_TOKENS = 1200


def load_basis(rje_id):
    with open(os.path.join(BASIS, "%s.txt" % rje_id), encoding="utf-8") as f:
        return f.read()


def cycles():
    import json
    out = []
    with open(CYCLES, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_gold():
    """The gold verdicts, keyed by close_id. NEVER read by check() — passing them anywhere near
    the prompt would be the oldest mistake in evaluation."""
    import json
    rows = {}
    with open(GOLD, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["close_id"]] = r
    return rows


def _citation_is_real(citation, basis_text):
    """Is the model's cited clause actually in the basis document, or did it write one? Pure code,
    so it costs nothing per run. Whitespace is normalised so a model reflowing a line it copied
    correctly is not scored as a fabrication."""
    if not citation:
        return None
    norm = " ".join(citation.split()).lower()
    hay = " ".join(basis_text.split()).lower()
    return norm in hay


def check(cfg, cycle, basis_text, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """Return the full record for one close cycle: a verdict per check, and what the call cost.

    `complete` is injectable so the eval harness, the app and the stub all drive the same code
    path.
    """
    msgs, parts = P.build(cycle, basis_text, prompt=prompt)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw)

    rows = []
    for c in P.CHECKS:
        got = parsed[c]
        citation = (got or {}).get("citation", "")
        rows.append({
            "check": c,
            "verdict": (got or {}).get("verdict"),          # None = never answered
            "citation": citation,
            "expected": (got or {}).get("expected"),
            "actual": (got or {}).get("actual"),
            "citation_in_basis": _citation_is_real(citation, basis_text),
        })

    answered = sum(1 for r in rows if r["verdict"] is not None)
    parsed_ok = bool((raw or "").strip()) and answered > 0
    return {
        "close_id": cycle["close_id"],
        "rje_id": cycle["rje_id"],
        "checks": rows,
        "answered": answered,
        "asked": len(P.CHECKS),
        "parsed": parsed_ok,
        "raw": raw,
        "parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "reasoning_tokens": (res.get("token_details") or {}).get("reasoning_tokens"),
        "token_details": res.get("token_details"),
        "model": res.get("model"),
    }


def summary(record):
    """The four numbers the app panel shows, computed in one place. clean + defect + unverifiable
    + no_verdict == checked, always — the same identity data-reconcile's summary() asserts, for the
    same reason: folding a silent model's non-answers into any one verdict would award it a score
    it did not earn."""
    rows = record["checks"]
    out = {"checked": len(rows), "clean": 0, "defect": 0, "unverifiable": 0, "no_verdict": 0}
    for r in rows:
        if r["verdict"] is None:
            out["no_verdict"] += 1
        else:
            out[r["verdict"]] += 1
    assert out["clean"] + out["defect"] + out["unverifiable"] + out["no_verdict"] == out["checked"]
    return out
