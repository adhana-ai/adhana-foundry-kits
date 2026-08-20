"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER VENDOR INQUIRY, NOT PER STAGE. The model reads the invoice's full 4-stage record
(match, approval, run_inclusion, remittance) and the vendor's inquiry text together, and fills one
small field set in one call: which of five stages actually governs right now, whether AP review is
required before the drafted reply can go out, what date (if any) the reply may state, and the reply
itself.

⚠︎ THE PRECEDENCE RULE IS THE WHOLE JOB, AND IT IS STATED TO THE MODEL EXPLICITLY RATHER THAN LEFT
IMPLICIT. Reading the four stages IN ORDER -- match, then approval, then run_inclusion, then
remittance -- and stopping at the first one that is not cleanly complete is not a shortcut to the
answer, it IS the answer. A later-stage field can carry a value that looks complete (a run_id and a
scheduled_date, a remittance_date and a reference) while an earlier stage is the one that actually
governs -- see tools/build_corpus.py for exactly how and how often that is planted. This is
deliberately a "read the whole record and apply the right precedence" task, not a "spot the lie"
task: nothing in the record is written to deceive, the fields are simply what they are, and getting
it right means reading match and approval before trusting what run_inclusion or remittance say.

⚠︎ THE FALSE "REMITTED" IS THE EXPENSIVE DIRECTION, NAMED TO THE MODEL. Telling a vendor an invoice
is paid when the true governing stage is an open match or approval exception is the one failure
this kit exists to catch -- see evals/scoring.py's `false_paid`. The system prompt says this in as
many words: never claim paid, or that payment is imminent, unless `remitted` is the actual current
stage.

⚠︎ THIS KIT NEVER RELEASES A PAYMENT, CHANGES A REMITTANCE DETAIL, OR COMMITS TO A DATE BEYOND THE
SCHEDULED RUN. The reply is informational only -- it reports the invoice's actual traced state, it
never promises to accelerate or move a payment off-cycle. See src/payrun.py's module docstring for
where that boundary is enforced in code, not just in this prompt.
"""
import json

STAGES = (
    "match_exception",
    "approval_exception",
    "awaiting_run_inclusion",
    "in_scheduled_run",
    "remitted",
)

STAGE_MEANINGS = {
    "match_exception": "match.matched is false -- the invoice has not cleared three-way match "
                       "and nothing downstream can be trusted regardless of what it shows.",
    "approval_exception": "match is clean, and approval.status is \"exception\" -- the invoice "
                          "is held on an approval problem, whatever run_inclusion or remittance "
                          "happen to contain.",
    "awaiting_run_inclusion": "match and approval are both clean, and run_inclusion.included is "
                              "false -- approved, but not yet placed on a scheduled payment run.",
    "in_scheduled_run": "match, approval and run_inclusion are all clean, and "
                        "remittance.remitted is false -- on a scheduled run with a real "
                        "scheduled_date, not yet paid.",
    "remitted": "all four stages are clean and remittance.remitted is true -- the payment has "
               "actually gone out.",
}

# requires_ap_review is DERIVED, never asked for independently -- true iff the governing stage is
# one of these two. Stated here once so src/payrun.py and evals/scoring.py read the same rule
# rather than each hard-coding it.
REVIEW_STAGES = ("match_exception", "approval_exception")

SYSTEM = (
    "You trace one vendor invoice through match, approval, payment-run inclusion and remittance, "
    "and draft a reply to the vendor's payment-status inquiry grounded in its actual traced "
    "state. You are given the invoice's full 4-stage record and the vendor's inquiry text.\n\n"
    "THE FOUR STAGES, READ IN THIS ORDER, STOPPING AT THE FIRST ONE THAT IS NOT CLEANLY COMPLETE\n"
    "  1. match            matched true/false, with a reason if false\n"
    "  2. approval          status approved/pending/exception, with a reason if exception\n"
    "  3. run_inclusion     included true/false; if true a run_id + scheduled_date, if false a "
    "reason\n"
    "  4. remittance        remitted true/false; if true a remittance_date + method + reference, "
    "if false a reason\n\n"
    "The TRUE current stage is whichever of these four is the actual bottleneck, read IN ORDER "
    "-- match first, then approval, then run_inclusion, then remittance. Stop at the first stage "
    "that is not cleanly complete. This is the trap: a later field can look complete -- a "
    "run_inclusion with a real run_id and scheduled_date, a remittance with a real date and "
    "reference -- while an EARLIER stage is the one that actually governs. A downstream field "
    "that looks done never overrides an earlier stage that is not. Read the whole record before "
    "answering; do not stop at the first field that looks reassuring.\n\n"
    "THE FIVE VALUES FOR current_stage, EXACTLY ONE APPLIES\n"
    "  match_exception          %s\n"
    "  approval_exception       %s\n"
    "  awaiting_run_inclusion   %s\n"
    "  in_scheduled_run         %s\n"
    "  remitted                 %s\n\n"
    "requires_ap_review is true if and only if current_stage is match_exception or "
    "approval_exception -- an open exception at either stage means the drafted reply needs AP "
    "review before it is sent to the vendor.\n\n"
    "THE REPLY MUST BE GROUNDED IN current_stage, NEVER IN A DOWNSTREAM FIELD ALONE\n"
    "  - Never claim the invoice is paid, or that payment is imminent, unless current_stage is "
    "remitted.\n"
    "  - If current_stage is in_scheduled_run, state ONLY the real scheduled_date from "
    "run_inclusion -- never an earlier or invented date, never \"accelerated\" or \"off-cycle\" "
    "language.\n"
    "  - If current_stage is remitted, state the real remittance_date and reference.\n"
    "  - If current_stage is match_exception or approval_exception, the reply must not state a "
    "payment timeline at all -- there is nothing to schedule yet -- and must say the item needs "
    "AP review.\n\n"
    "stated_date is the one date, if any, the reply states: the real scheduled_date for "
    "in_scheduled_run, the real remittance_date for remitted, or null for the other three stages "
    "-- there is no date to state for an exception or for a stage still awaiting run inclusion.\n\n"
    "You never release a payment, never change a remittance detail, and never commit to a date "
    "beyond the invoice's own scheduled run. The reply is informational only -- it reports the "
    "invoice's actual traced state to the vendor, it never promises to accelerate or move a "
    "payment off-cycle, and it is never sent without AP review when requires_ap_review is true."
) % tuple(STAGE_MEANINGS[s] for s in STAGES)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _stage_block(inv):
    m, a, r, x = inv["match"], inv["approval"], inv["run_inclusion"], inv["remittance"]
    return (
        "INVOICE %s (vendor %s, PO %s, amount $%.2f, submitted %s)\n"
        "1. match: matched=%s%s\n"
        "2. approval: status=%s%s\n"
        "3. run_inclusion: included=%s%s\n"
        "4. remittance: remitted=%s%s\n"
        "VENDOR INQUIRY: %s\n"
        % (inv["invoice_id"], inv["vendor_name"], inv["po_number"], inv["amount"],
           inv["submitted_date"],
           m["matched"], ("" if m["matched"] else "  reason: %s" % m["reason"]),
           a["status"], ("" if a["status"] != "exception" else "  reason: %s" % a["reason"]),
           r["included"],
           ("  run_id=%s scheduled_date=%s" % (r["run_id"], r["scheduled_date"])
            if r["included"] else "  reason: %s" % r["reason"]),
           x["remitted"],
           ("  remittance_date=%s method=%s reference=%s"
            % (x["remittance_date"], x["method"], x["reference"])
            if x["remitted"] else "  reason: %s" % x["reason"]),
           inv["inquiry"])
    )


def build(inv, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    record_block = _stage_block(inv)
    user = (
        "Trace the invoice below and draft a reply to the vendor's inquiry.\n\n"
        "Return a JSON object with exactly four keys: \"current_stage\" (one of: %s), "
        "\"requires_ap_review\" (true or false), \"stated_date\" (the one date the reply states, "
        "as it appears in the record, or null), \"reply\" (the drafted reply text, one or two "
        "sentences).\n\n%s" % (", ".join(STAGES), record_block)
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "record", "text": record_block},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the field set out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields an all-None result -- read as "this call produced no
    answer", never as evidence about the invoice -- never a regex fallback that scrapes a
    plausible-looking stage out of raw text. That would silently turn a broken call into a
    mediocre tracer.
    """
    out = {"current_stage": None, "requires_ap_review": None, "stated_date": None, "reply": None}
    if not raw:
        return out
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return out
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return out
    stage = str(obj.get("current_stage", "") or "").strip().lower().replace(" ", "_").replace(
        "-", "_")
    if stage in STAGES:
        out["current_stage"] = stage
    rev = obj.get("requires_ap_review")
    if isinstance(rev, bool):
        out["requires_ap_review"] = rev
    sd = obj.get("stated_date")
    out["stated_date"] = sd if (sd is None or isinstance(sd, str)) else None
    reply = obj.get("reply")
    out["reply"] = reply if isinstance(reply, str) else None
    return out
