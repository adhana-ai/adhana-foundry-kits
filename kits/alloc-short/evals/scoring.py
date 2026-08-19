"""Score a set of drafted briefs against gold. Pure code, shared by evals/baseline.py and
evals/run.py so the free floor and the real run are graded by the identical function. Same
discipline gap-brief's evals/scoring.py and data-reconcile's evals/scoring.py both state for
their own scorers.

Three axes, per src/rubric.py's RUBRIC_AXES, plus TWO guardrail metrics reported on their own,
never folded into either axis:

    flag_completeness       recall/precision of the EVENT SET the brief covers, against the
                            events src/allocate.py actually flagged.
    cause_tag_agreement     for events both gold and the brief cover, does the cause match --
                            split by whether gold's own cause was 'unknown' or traceable.
    narrative_faithfulness  does every quantified claim in the narrative trace to a number
                            actually present in the packed event list.
    fabricated_cause        (guardrail) a non-'unknown' cause whose citations are not both real,
                            SKU-relevant lines from that session's own notes.
    conservation            (guardrail) does every event's code-computed split sum to exactly
                            min(available_units, total_ask) -- true independent of the model call,
                            checked here so a committed eval result carries the proof rather than
                            asserting it in prose.

⚑ A CITATION MUST BE BOTH REAL AND RELEVANT, NOT MERELY REAL. Every planted cause-note line in
this corpus opens with "<sku>: ..." (see tools/build_corpus.py), so a citation that is a genuine
substring of the notes log but does not name the SKU it is cited for is citing someone else's
evidence -- caught here, not folded into a plain substring check, because that check alone would
pass a real-but-wrong-SKU citation.
"""
import re

# ⚑ ID TOKENS ARE MASKED OUT BEFORE NUMBER EXTRACTION, NOT EXCLUDED VIA LOOKBEHIND -- FIXED AFTER
# READING r001-alloc-short's OWN RESULT TWICE. A first attempt used a negative lookbehind
# (?<![A-Z]-) on NUM_RE directly, and it did not work: the lookbehind only blocks a match from
# STARTING at the id's first digit, so the regex engine simply started matching one character
# later and returned "111" out of "EV-0111" instead of skipping the token -- a leading zero
# silently vanishing was the tell. Every id in this corpus is an uppercase prefix and a hyphen --
# EV-0111, ST-092, SESS-012 -- and the prompt explicitly asks the model to refer to events by id
# in its narrative, the same thing every sibling kit's prompt asks. ID_RE strips the WHOLE token
# out of the text before NUM_RE ever runs, so no fragment of it can be mistaken for a quantity.
ID_RE = re.compile(r"\b[A-Z]+-\d+\b")
NUM_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _norm(s):
    """Whitespace/case-collapsed, and stripped of a leading '- ' bullet marker -- added after a
    real pro-tier reply quoted a notes line byte-for-byte but WITH the leading '- ' that
    src/prompt.py::_notes_block prints when it shows the notes log to the model. That marker is
    this kit's own display formatting, not the notes line itself and not something the model
    invented; grading it as a fabrication would be scoring the prompt's presentation against the
    model for quoting exactly what it was shown. No real notes line in this corpus starts with a
    literal hyphen, so the strip cannot hide a genuine mismatch."""
    s = " ".join((s or "").split()).lower()
    return s[2:] if s.startswith("- ") else s


def citation_is_real(citation, notes_text):
    if not citation:
        return False
    return _norm(citation) in _norm(notes_text)


def citation_is_relevant(citation, sku):
    if not citation or not sku:
        return False
    return _norm(sku) in _norm(citation)


def _extract_numbers(text):
    out = []
    if not text:
        return out
    text = ID_RE.sub(" ", text)
    for m in NUM_RE.finditer(text):
        tok = m.group(0)
        is_pct = tok.endswith("%")
        raw = tok[:-1] if is_pct else tok
        raw = raw.lstrip("$").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        if val == 0:
            continue
        out.append((val, is_pct))
    return out


def _allowed_pool(packed):
    """The numbers a faithful narrative is allowed to state: every unit figure in the packed
    event list, the count of events, any digit run in the session's own metadata (week,
    session_id), and every number stated in the merchant notes log -- all three carve-outs added
    after reading a real reply rather than guessed in advance, same discipline gap-brief's own
    _allowed_pool states for its period/cycle_id carve-out.

    ⚑ THE NOTES-LOG NUMBERS, ADDED AFTER READING r001-alloc-short's OWN RESULT. Two real replies
    stated a supply-shortfall size ("about 203 units under what was expected") that is not
    computable from the structured event fields at all -- it is a fact stated only in the notes
    line the model read, verbatim, to decide the cause. The notes log is `packed["notes"]`, part
    of what was actually sent, so a number quoted from it is traceable to the input exactly as
    surely as a number quoted from the structured event fields is. Flagging it as invented would
    be scoring the prompt's own design against the model for correctly doing the one thing the
    prompt explicitly asks it to do -- read the notes and use them."""
    nums, pcts = set(), set()
    for n in packed.get("notes") or []:
        for tok in re.findall(r"\d[\d,]*", n):
            try:
                nums.add(int(tok.replace(",", "")))
            except ValueError:
                pass
    for e in packed["events"]:
        nums.add(e["available_units"])
        nums.add(e["total_ask"])
        # The shortfall is not itself a field the model was handed, but it is unambiguously
        # computable from two fields that were (total_ask, available_units) -- same allowance
        # gap-brief's own pool gives derived figures that are one subtraction away from what was
        # actually sent, not an invitation to state anything uncomputed.
        nums.add(e["total_ask"] - e["available_units"])
        for p in e["per_store"]:
            nums.add(p["ask_units"])
            nums.add(p["allocated_units"])
        nums.add(len(e["floor_breach_stores"]))
        # "N stores" -- a real reply counted the per-event store list, same allowance as
        # "N events" below for the session-level count.
        nums.add(len(e["per_store"]))
    nums.add(len(packed["events"]))
    # A session-wide "N units asked across all stores" total is a natural aggregate claim, and a
    # real reply made it twice (1,832 and 1,497 -- both the exact sum of that session's own
    # total_ask figures). It is one addition away from numbers already in the pool, same
    # allowance as the per-event shortfall above.
    nums.add(sum(e["total_ask"] for e in packed["events"]))
    nums.add(sum(e["available_units"] for e in packed["events"]))
    for field in ("week", "session_id", "region"):
        for tok in re.findall(r"\d+", str(packed.get(field, ""))):
            nums.add(int(tok))
    # The equity floor is a FIXED POLICY CONSTANT the model is told verbatim in the system
    # prompt ("...then check a 40% equity floor"), not a per-session figure -- a real reply
    # stated "the 40% equity floor" and it was flagged as an invented percentage because nothing
    # in the packed EVENT data carries it. It is input the model was handed exactly as surely as
    # anything in the packed dict; see src/prompt.py::SYSTEM for the exact sentence.
    from src.allocate import EQUITY_FLOOR_PCT
    pcts.add(EQUITY_FLOOR_PCT)
    return nums, pcts


def _amount_matches(val, is_pct, nums, pcts):
    pool = pcts if is_pct else nums
    for allowed in pool:
        tol = 1.5 if is_pct else max(2.0, 0.02 * abs(allowed))
        if abs(val - allowed) <= tol:
            return True
    return False


def narrative_faithfulness(narrative, packed):
    """Returns (faithful: bool or None, unmatched). None means no narrative was produced at all
    -- a distinct, worse state than an unfaithful one, never folded in as a pass."""
    if not narrative:
        return None, []
    nums, pcts = _allowed_pool(packed)
    extracted = _extract_numbers(narrative)
    unmatched = [n for n in extracted if not _amount_matches(n[0], n[1], nums, pcts)]
    return (len(unmatched) == 0), unmatched


def conservation(gold):
    """Independent of the model entirely -- reads the gold file's own recorded conservation_ok
    per event, which tools/build_corpus.py stamped straight from src/allocate.py at generation
    time. Reported alongside the model-graded axes so a committed result carries the proof."""
    total = ok = 0
    for g in gold.values():
        for ev in g["events"]:
            total += 1
            if ev.get("conservation_ok", True):
                ok += 1
    return {"events": total, "conserved": ok,
           "conservation_pct": round(100.0 * ok / total, 1) if total else None}


def score(records, gold, notes_by_id):
    """`records` are evals/run.py's per-session output dicts (record["answer"]["events"/
    "narrative"], record["packed"]). `gold` and `notes_by_id` are keyed by session_id."""
    tp_total = fp_total = fn_total = 0
    cause_correct = cause_total = 0
    unknown_correct = unknown_total = 0
    traceable_correct = traceable_total = 0
    fabricated = 0
    fabricated_examples = []
    protect_echo_correct = protect_echo_total = 0
    narratives_faithful = narratives_scored = narratives_missing = 0
    per_session = []

    for rec in records:
        sid = rec["session_id"]
        g = gold.get(sid)
        if not g:
            continue
        notes_text = "\n".join(notes_by_id.get(sid, []))
        gold_flagged = {gg["event_id"]: gg for gg in g["events"] if gg["flagged"]}
        model_events = {me["event_id"]: me for me in rec["answer"]["events"] if me.get("event_id")}

        gold_ids = set(gold_flagged)
        model_ids = set(model_events)
        tp = gold_ids & model_ids
        fp = model_ids - gold_ids
        fn = gold_ids - model_ids
        tp_total += len(tp)
        fp_total += len(fp)
        fn_total += len(fn)

        sess_cause_correct = sess_fabricated = 0
        for event_id in tp:
            gg, me = gold_flagged[event_id], model_events[event_id]
            gold_cause = gg["true_cause"] or "unknown"
            model_cause = me.get("cause")
            cause_total += 1
            is_correct = model_cause == gold_cause
            if is_correct:
                cause_correct += 1
                sess_cause_correct += 1
            if gold_cause == "unknown":
                unknown_total += 1
                if is_correct:
                    unknown_correct += 1
            else:
                traceable_total += 1
                if is_correct:
                    traceable_correct += 1

            if model_cause and model_cause != "unknown":
                c1_ok = (citation_is_real(me.get("citation_1"), notes_text)
                        and citation_is_relevant(me.get("citation_1"), gg["sku"]))
                c2_ok = (citation_is_real(me.get("citation_2"), notes_text)
                        and citation_is_relevant(me.get("citation_2"), gg["sku"]))
                if not (c1_ok and c2_ok):
                    fabricated += 1
                    sess_fabricated += 1
                    if len(fabricated_examples) < 10:
                        fabricated_examples.append({
                            "session_id": sid, "event_id": event_id, "cause": model_cause,
                            "citation_1": me.get("citation_1"), "citation_2": me.get("citation_2"),
                            "citation_1_ok": c1_ok, "citation_2_ok": c2_ok,
                        })

        faithful, unmatched = narrative_faithfulness(rec["answer"].get("narrative"), rec["packed"])
        if faithful is None:
            narratives_missing += 1
        else:
            narratives_scored += 1
            if faithful:
                narratives_faithful += 1

        per_session.append({
            "session_id": sid, "gold_flagged": len(gold_ids), "model_covered": len(model_ids),
            "true_positive": len(tp), "false_positive": len(fp), "false_negative": len(fn),
            "cause_correct": sess_cause_correct, "fabricated_cause": sess_fabricated,
            "narrative_faithful": faithful, "narrative_unmatched": unmatched,
        })

    def pct(n, d):
        return round(100.0 * n / d, 1) if d else None

    cons = conservation(gold)
    overall = {
        "sessions_scored": len(per_session),
        "gold_flagged_total": tp_total + fn_total,
        "model_covered_total": tp_total + fp_total,
        "true_positive": tp_total, "false_positive": fp_total, "false_negative": fn_total,
        "flag_completeness_recall_pct": pct(tp_total, tp_total + fn_total),
        "flag_completeness_precision_pct": pct(tp_total, tp_total + fp_total),
        "cause_tag_agreement_pct": pct(cause_correct, cause_total),
        "cause_tag_agreement_unknown_pct": pct(unknown_correct, unknown_total),
        "cause_tag_agreement_traceable_pct": pct(traceable_correct, traceable_total),
        "unknown_total": unknown_total, "traceable_total": traceable_total,
        "fabricated_cause": fabricated,
        "fabricated_cause_rate_pct": pct(fabricated, cause_total),
        "narrative_faithful": narratives_faithful,
        "narrative_scored": narratives_scored,
        "narrative_missing": narratives_missing,
        "narrative_faithfulness_pct": pct(narratives_faithful, narratives_scored),
        "conservation_events": cons["events"], "conservation_ok": cons["conserved"],
        "conservation_pct": cons["conservation_pct"],
    }
    return {"overall": overall, "per_session": per_session, "fabricated_examples": fabricated_examples}
