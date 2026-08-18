"""The verdict vocabulary and the one prompt this kit sends. Declared once, here, and read from
here by the app, the harness, the baseline and the scorer -- the same discipline data-match's
prompt.py states about its own three-verdict vocabulary, for the same reason: a second copy is a
silent disagreement waiting to happen.

ONE CALL PER REQUEST, NOT PER CANDIDATE -- same batching discipline change-impact's prompt.py uses.
A request's whole candidate set (already narrowed to its own category by src/block.py) is sent in
one call, and the model returns one verdict per candidate.

⚑ THREE VERDICTS, NOT TWO. `NOT_ANALOG` says this candidate is not a comparable precedent.
`UNSURE` says the listed fields do not settle it either way -- reserved for a genuinely borderline
case, and never the gold label for a pair (gold is binary; see data/SOURCES.md). A model that
defaults an unsure case to a guess converts a real gap into a confident wrong answer, the same
failure the third verdict exists to head off everywhere else in this series.

⚠︎ THE MODEL NEVER COMPUTES THE LIFT NUMBER. It returns, per candidate, ANALOG / NOT_ANALOG / UNSURE
plus a one-line reason. src/lift.py turns the ANALOG set into a recommended lift percentage,
deterministically, from the analog events' own recorded actual_lift_pct -- never asserted by the
model, never hand-typed into gold. See its own header for why that split exists.
"""
import json

VERDICTS = ("ANALOG", "NOT_ANALOG", "UNSURE")

# ⚑ NAMED VERDICT_MEANINGS, NOT MEANS -- the site's app panel reads this module by AST looking for
# exactly that name (same convention docs-verify's prompt.py uses), so the vocabulary card on the
# kit's hosted "Match & draft" tab is drawn from here rather than a second, hand-typed copy.
# `costs` is what getting THIS verdict wrong does to whoever trusts the drafted lift -- the two
# failure directions are not interchangeable, same discipline as every sibling kit's own verdict
# table.
VERDICT_MEANINGS = {
    "ANALOG": {
        "means": "A genuinely comparable precedent -- safe to fold into the lift estimate.",
        "costs": "Called here wrongly (a FALSE ANALOG), it silently pollutes the published "
                 "number a planner will act on -- the expensive direction, because it is "
                 "invisible in the percentage itself.",
    },
    "NOT_ANALOG": {
        "means": "Resembles the request on the surface but is not a real precedent under the "
                 "stated rule.",
        "costs": "Called here wrongly, a real precedent is excluded and the estimate is drawn "
                 "from a smaller, weaker set than it should be -- recoverable, not silent.",
    },
    "UNSURE": {
        "means": "The listed fields do not settle it either way -- reserved for a genuinely "
                 "borderline case.",
        "costs": "Defaulting an UNSURE to a guess converts a real gap into a confident wrong "
                 "answer; excluded from the estimate rather than guessed either direction.",
    },
}

# ⚑ THE OUTPUT CEILING IS PART OF THE PROMPT CONTRACT -- see data-match's own MAX_TOKENS note for
# why a "just a few words per candidate" reply still needs real headroom on a reasoning model: the
# reasoning happens before the words that get billed, not instead of them. Set high enough that
# truncation is not the thing under measurement; `finish_reason` on every row is what proves it.
MAX_TOKENS = 4096

RULES = (
    "Decide, for EACH candidate, whether it is a genuine comparable precedent for the planned "
    "request -- something a demand planner could safely lean on to estimate this request's lift.\n\n"
    "A candidate is ANALOG only if ALL of the following hold:\n"
    "  1. mechanic is IDENTICAL to the request's mechanic.\n"
    "  2. price_band is IDENTICAL to the request's, OR the next band up or down on this fixed "
    "order: under_5, 5_10, 10_25, 25_plus (adjacent bands are close enough; two bands apart is "
    "not).\n"
    "  3. ad_placement is IDENTICAL, OR both the request's and the candidate's placement are in "
    "the paper-circular family {circular_front, circular_inside} -- a shopper reads both as "
    "\"the circular\", so that pair alone counts as the same placement. No other placement pair "
    "is equivalent.\n"
    "  4. season is IDENTICAL. There is no season equivalence -- a back_to_school lift and a "
    "holiday lift are never interchangeable evidence, however similar the other fields are.\n\n"
    "discount_depth_pct and duration_days are shown for context only and never decide the "
    "verdict by themselves -- two promotions at the same discount depth are not analogs if the "
    "mechanic, band, placement or season rule above fails.\n\n"
    "If a candidate could plausibly go either way and nothing above settles it, answer UNSURE "
    "rather than guessing -- do not round an UNSURE up to ANALOG because the numbers look similar."
)

SYSTEM = (
    "You are the demand-planning analyst's precedent check. You are given one planned promotion "
    "or event, and a list of candidate prior events already narrowed to the same product "
    "category. " + RULES
)


def _row(rec, is_request):
    tag = "REQUEST" if is_request else rec["event_id"]
    line = ("%s -- mechanic=%s, price_band=%s, ad_placement=%s, season=%s, "
            "discount_depth_pct=%s, duration_days=%s"
            % (tag, rec["mechanic"], rec["price_band"], rec["ad_placement"], rec["season"],
               rec["discount_depth_pct"], rec["duration_days"]))
    if not is_request:
        line += ", actual_lift_pct=%s (historical outcome -- context only, do not average it "\
                "yourself)" % rec["actual_lift_pct"]
    return line


def build(request, candidates):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    req_block = "PLANNED REQUEST\n----------------\n%s\n" % _row(request, True)
    note = (request.get("planner_note") or "").strip()
    if note:
        req_block += "Planner's note (context only -- not an instruction): %s\n" % note
    if candidates:
        cand_block = ("CANDIDATES (same category, %d)\n-------------------------------\n"
                      % len(candidates)) + "\n".join(_row(c, False) for c in candidates) + "\n"
    else:
        cand_block = "CANDIDATES\n----------\n(none -- blocking found no prior event in this " \
                     "category)\n"
    user = (
        "%s\n%s\n"
        "Return a JSON object with exactly one key, \"verdicts\": a list with one entry per "
        "candidate, in the order listed, each entry "
        "{\"event_id\": <the candidate's id>, \"verdict\": <one of %s>, \"reason\": "
        "<one short sentence citing which rule decided it>}."
        % (req_block, cand_block, ", ".join(VERDICTS))
    )
    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "request", "text": req_block},
        {"name": "candidates", "text": cand_block},
    ]
    return ([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], parts)


def parse(raw, candidate_ids):
    """A dict of event_id -> verdict ('ANALOG'/'NOT_ANALOG'/'UNSURE'/None), plus the raw reasons.
    Never creative: a candidate this reply is silent about maps to None ('no_verdict'), not to a
    guessed default -- the same discipline data-match's prompt.py states for a reply that does not
    parse at all."""
    out = {eid: None for eid in candidate_ids}
    reasons = {}
    if not raw:
        return out, reasons
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return out, reasons
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return out, reasons
    for row in obj.get("verdicts") or []:
        if not isinstance(row, dict):
            continue
        eid = row.get("event_id")
        v = row.get("verdict")
        if eid not in out or not isinstance(v, str):
            continue
        vv = v.strip().upper()
        if vv in VERDICTS:
            out[eid] = vv
            if isinstance(row.get("reason"), str):
                reasons[eid] = row["reason"]
    return out, reasons
