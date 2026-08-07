"""The AI layer: two document versions in, one materiality verdict out. The whole model surface.

⚑ THE GUARDRAIL LIVES HERE, NOT IN THE EVAL — same reasoning as docs-route's route.py. `decide()`
runs diff.primary() to find the change, then applies the confidence floor to the model's verdict
before anything downstream sees it, so the number this kit publishes comes from the same code
path the app uses.

⚑ A PAIR WITH NO DETECTABLE DIFFERENCE IS A REAL STATE, NOT AN ERROR. If diff.primary() finds
nothing — the two texts tokenise identically — `decide()` returns state "no_change" rather than
calling a model about nothing. tools/build_corpus.py should not ship a pair like this, but a
run must not crash if one slips through; it must say so.
"""
import json
import os

from . import adapters, diff as D, prompt as P, materiality as MT

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ THE OUTPUT CEILING. A materiality verdict is a level, a number and one short sentence — the
# same shape as docs-route's routing decision, so it inherits docs-route's measured ceiling
# rather than guessing a new one: see route.py in that kit for the 400-was-too-low finding.
MAX_TOKENS = 1200

# ⚑ THE CONFIDENCE FLOOR — a starting position, not a finding, for the same reason docs-route's
# is: tuning it against this eval set and publishing the tuned number would fit a threshold to
# the documents it is scored on. Kept at the same value so a reader comparing the two kits is
# comparing the mechanism, not two different choices dressed up as one.
CONFIDENCE_FLOOR = 0.6


def pairs():
    """Every document pair the corpus ships, as (pair_id, v1_id, v2_id), pair_id sorted."""
    manifest_path = os.path.join(CORPUS, "manifest.json")
    if not os.path.exists(manifest_path):
        return []
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    return sorted((p["pair_id"], p["v1_id"], p["v2_id"]) for p in manifest.get("pairs", []))


def load_version(doc_id):
    with open(os.path.join(CORPUS, "%s.txt" % doc_id), encoding="utf-8") as f:
        return f.read()


def decide(cfg, v1_text, v2_text, complete=None, floor=CONFIDENCE_FLOOR):
    """Return the full record for one pair: the change found, the verdict, why, and what it cost."""
    span = D.primary(v1_text, v2_text)
    if span is None:
        return {"state": "no_change", "span": None, "model_materiality": None,
                "materiality": None, "escalated": False, "confidence": None, "why": "",
                "floor": floor, "offered": None, "raw_text": "",
                "input_tokens": 0, "output_tokens": 0}

    system, user = P.build(span)
    call = complete or adapters.complete
    reply = call(cfg, system, user, max_tokens=MAX_TOKENS)
    parsed = P.parse(reply.get("text"))

    # The guardrail. Kept exactly as docs-route keeps it: BOTH the model's answer and what the
    # system did with it are recorded, because a floor that silently overwrote the model's answer
    # would make its own effect unmeasurable.
    verdict, escalated = parsed["materiality"], False
    if parsed["state"] == "ok" and floor is not None:
        if parsed["confidence"] is None or parsed["confidence"] < floor:
            verdict, escalated = None, True

    return {
        "state": parsed["state"],
        "span": span,
        "model_materiality": parsed["materiality"],
        "materiality": verdict,
        "escalated": escalated,
        "confidence": parsed["confidence"],
        "why": parsed["why"],
        "floor": floor,
        "offered": parsed.get("offered"),
        "raw_text": parsed.get("raw", ""),
        "input_tokens": reply.get("input_tokens"),
        "output_tokens": reply.get("output_tokens"),
    }


def outcome(rec):
    """One word for what happened to a pair, for the app and the run log — same third-outcome
    discipline as docs-route's outcome(): escalated is neither a win nor a loss."""
    if rec["state"] == "no_change":
        return "no_change"
    if rec["escalated"]:
        return "escalated"
    if rec["state"] == "abstained":
        return "abstained"
    if rec["state"] in ("offmenu", "unparsed"):
        return rec["state"]
    return "flagged"


def summary_line(pair_id, rec):
    label = MT.label_of(rec["materiality"]) if rec["materiality"] else "—"
    conf = "%.2f" % rec["confidence"] if rec["confidence"] is not None else " n/a"
    return "%-14s %-10s %-10s conf %s" % (pair_id, outcome(rec), label, conf)


def as_json(rec):
    return json.dumps(rec, ensure_ascii=False)
