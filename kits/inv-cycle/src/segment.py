"""SEAM 1 -- the cut. Deciding which cause one variance event's own transaction history actually
supports. Pure code, no model -- same discipline gap-brief's own src/segment.py keeps: the thing
that decides what the CORRECT answer is must be arithmetic and flag-checks on the log itself,
never something the model asserted, and never a `true_cause` variable typed once and trusted.

⚑ WHY THIS MODULE EXISTS TWICE OVER. `tools/build_corpus.py` calls `classify()` on the record it
just assembled to WRITE gold -- it does not hand-author a cause and copy it in. `evals/scoring.py`
calls `line_supports_cause()` to check whether the MODEL's cited line index actually evidences the
cause it claimed, using the identical rule. One function, two callers, so the planted answer and
the graded answer can never quietly drift apart.

⚑ ONE PRECEDENCE ORDER, STATED ONCE -- this is what resolves the trap. `uom_error` requires an
explicit unit-of-measure-mismatch flag on a log line, not merely "the variance divides evenly by
a case-pack size" -- a bare multiple is a coincidence this corpus plants deliberately for roughly
40-45% of unrecorded_transfer cases. `unrecorded_transfer`'s own flag is checked FIRST, so an event
carrying both signals (the transfer hint AND a coincidental case-pack multiple, with no genuine
uom-mismatch flag) classifies as unrecorded_transfer -- exactly the failure mode a model that
pattern-matches on the multiple alone will get wrong. See tools/build_corpus.py for how the log
lines are constructed to carry these flags.
"""

CASE_PACK_SIZES = (12, 24)


def is_case_pack_multiple(variance_qty, pack_sizes=CASE_PACK_SIZES):
    """True when |variance_qty| divides evenly by one of the stated case-pack sizes. This is the
    SURFACE signal the trap trades on -- true for both genuine uom_error events and trap
    unrecorded_transfer events, which is the whole point: being true here is never sufficient by
    itself for uom_error. See classify()."""
    v = abs(variance_qty)
    return v != 0 and any(v % p == 0 for p in pack_sizes)


def accounted_change(log):
    """The net quantity change the log itself claims, signed the same way variance_qty is
    (system minus counted): a receiving or transfer-in adds to on-hand (so it REDUCES a
    system-over-counted variance the same way counting more would), a transfer-out or a scan/pick/
    sale removes from on-hand. Kept as a single arithmetic pass so unscanned_movement's residual
    check and this module's docstring agree with each other by construction.

    ⚑ PUBLIC, NOT PRIVATE -- tools/build_corpus.py calls this directly to SIZE an
    unscanned_movement event's residual deliberately (variance_qty = accounted_change(log) plus a
    chosen nonzero residual), rather than picking variance_qty independently and hoping it happens
    to disagree with the log's own arithmetic."""
    total = 0
    for line in log:
        t = line["type"]
        if t == "receiving":
            total += line["qty"]
        elif t == "transfer":
            total += line["qty"] if line["direction"] == "in" else -line["qty"]
        elif t == "scan":
            total -= line["qty"]
        elif t == "adjustment" and line.get("flag") not in ("receiving_correction",
                                                             "counterpart_activity", "uom_note"):
            # A plain, unflagged adjustment (noise, or a routine prior correction) participates
            # in the arithmetic like any other posted change. A FLAGGED adjustment line is
            # evidence about the variance itself, not a posted movement to sum -- counting it here
            # too would double-count the exact thing classify() is trying to explain.
            total += line["qty"]
    return total


def line_supports_cause(event, idx, cause):
    """Does log line `idx` actually evidence `cause` for this event -- the CORRECT line, not
    merely a REAL one. `evals/scoring.py` calls this on every citation the model returns, and
    tools/build_corpus.py calls it (via classify()) to build gold in the first place."""
    log = event["log"]
    if idx is None or not (0 <= idx < len(log)):
        return False
    line = log[idx]
    if cause == "mis_receipt":
        return line.get("flag") == "receiving_correction"
    if cause == "unrecorded_transfer":
        return line.get("flag") == "counterpart_activity"
    if cause == "uom_error":
        return line.get("flag") == "uom_note"
    if cause == "unscanned_movement":
        return line["type"] == "scan"
    return False          # 'unresolved' cites nothing; no line "supports" it


def classify(event):
    """The five-way rule, run once, over one event's own log and variance_qty. Returns
    {"cause": <one of rubric.CAUSE_VOCAB>, "citations": [idx, ...]} -- citations is exactly the
    set of line indices classify() itself would call correct for that cause, so gold is always
    self-consistent with line_supports_cause() by construction, never a separately typed list.

    Precedence, in order, and why: a flagged receiving-correction line is the least ambiguous
    signal available (mis_receipt), so it is checked first. A flagged counterpart-activity line
    is checked NEXT -- before the uom multiple check -- which is the line that resolves the trap.
    A genuine uom-mismatch flag is checked third. Only once none of those three specific flags are
    present does the module fall back to the residual-arithmetic check for unscanned_movement, and
    only when there is at least one scan-type line to point to. Anything left over is unresolved.
    """
    log = event["log"]

    for i, line in enumerate(log):
        if line.get("flag") == "receiving_correction":
            return {"cause": "mis_receipt", "citations": [i]}

    for i, line in enumerate(log):
        if line.get("flag") == "counterpart_activity":
            return {"cause": "unrecorded_transfer", "citations": [i]}

    for i, line in enumerate(log):
        if line.get("flag") == "uom_note" and is_case_pack_multiple(event["variance_qty"]):
            return {"cause": "uom_error", "citations": [i]}

    scan_idx = [i for i, line in enumerate(log) if line["type"] == "scan"]
    if scan_idx and accounted_change(log) != event["variance_qty"]:
        return {"cause": "unscanned_movement", "citations": scan_idx[:2]}

    return {"cause": "unresolved", "citations": []}
