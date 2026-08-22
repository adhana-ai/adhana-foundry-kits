"""Extract one progress-payment package's fields: segment, select, prompt, one model call, then a
pure-code business-condition check downstream. This is the whole AI layer of the kit --
everything above it (segment, select) and below it (the hold flag) is pure code.

MAX_TOKENS -- MEASURED, NOT GUESSED, AND THE MEASUREMENT MOVED IT.

A three-package calibration run was fired before either scored run, precisely so this number
would not be a guess: results/eval-c000-calibration.json records output tokens between 981 and
1068 across the three packages, for an eleven-key JSON record. That is three to four times what
the sibling extraction kits
in this series need for a record of the same SHAPE, and the reason is that this task is not
shaped the same at all -- the model works the five-condition coverage rule through four or five
parties in the open before it answers, so most of the reply is the working rather than the record.

3000 is therefore roughly 2.8x the largest reply actually observed, on a task whose reply length
scales with the number of parties on the package (3 to 5 here). Anything much tighter would start
truncating the packages with the most parties, which are exactly the ones worth getting right.
evals/run.py records `finish_reason` on every call, records the run's own min and max output
tokens beside the cap, and marks a reply that hit the ceiling as CUT OFF AT THE CEILING rather
than as an unexplained parse failure.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 3000

WAIVER_TYPES = ("conditional_progress", "unconditional_progress",
                "conditional_final", "unconditional_final")

GAP_REASONS = ("no_waiver_on_file", "notice_after_waiver", "period_short", "amount_short",
               "conditional_stale")


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(pkg_id):
    with open(os.path.join(CORPUS, "%s.txt" % pkg_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def spannable(field):
    """Whether a value for this field can honestly be located back to the document.

    ⚠︎ IT IS DECLARED, NOT DERIVED FROM THE TYPE, and the difference is a real defect this kit
    would otherwise have shipped. `parties_uncovered` is a NUMBER, so a type rule would call it
    spannable -- and searching a package for "2" finds `Tier: 2` on the first party every time.
    A span pointing at a tier number for a derived count is worse than no span: it invites a
    reader to check, and the check appears to succeed.
    """
    if "spannable" in field:
        return bool(field["spannable"])
    return field.get("type") != "enum"


def coverage_status(waiver_type, waiver_amount, waiver_through, waiver_signed, notice_date,
                    amount_due, period_through, prior_cleared, joint_check):
    """THE RULE, in one place. tools/build_corpus.py::coverage_status() is the same function, used
    to write gold; data/fields.json and src/prompt.py state it to the model in words. Three
    readers, one definition, so the corpus, the prompt and the guardrail cannot drift apart about
    what "covered" means.

    Dates are ISO strings (YYYY-MM-DD) or None; amounts are floats in dollars. Returns one of
    GAP_REASONS, "covered", or None when a value the rule needs is missing or malformed.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED COVERAGE RULE, NOT ANY JURISDICTION'S LAW. Lien waiver
    requirements vary by jurisdiction and several places prescribe the form by statute. It
    determines nobody's lien rights; it assembles the picture and names the gaps.
    """
    if waiver_type == "none":
        return "no_waiver_on_file"
    if waiver_type not in WAIVER_TYPES:
        return None
    if notice_date and waiver_signed and notice_date > waiver_signed:
        return "notice_after_waiver"
    if waiver_type.endswith("_progress"):
        if not waiver_through or not period_through or waiver_through < period_through:
            return "period_short"
    if waiver_amount is None or amount_due is None:
        return None
    if waiver_amount + 0.005 < amount_due:
        return "amount_short"
    if waiver_type.startswith("conditional_") and (prior_cleared == "yes" or joint_check == "yes"):
        return "conditional_stale"
    return "covered"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as its sibling extraction kits in
    this series: it asks "is this the package somebody has to stop today", not "does this reply
    contradict itself".

    THE CONDITION: a package with at least one uncovered party that is SCHEDULED to be released
    this cycle.

    A package with a gap that is already on hold is not news -- somebody has stopped it. The same
    gap on a package scheduled to go out this cycle is the one a payment coordinator has to pull
    back today, before the money moves.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANY GENERAL CONTRACTOR'S RELEASE POLICY AND NOT
    A LEGAL TEST. No jurisdiction's statute, no filed subcontract and no real payment procedure
    was consulted, and none is reproduced. A real payment desk weighs the dollar size of the
    exposure, how far down the tiers the gap sits, whether a bond covers it and what the
    subcontract says about withholding; this is two values and an AND, chosen because it is the
    smallest rule that is genuinely useful and readable off one reply.

    ⚠︎ AND IT ROUTES, IT DOES NOT AUTHORISE. Nothing here releases a payment, and a package with
    no gap is not thereby cleared for release -- it is a package this kit found nothing to say
    about.

    Returns True / False, or None when the reply is missing something the rule needs -- an
    unknown is not a pass.
    """
    n = values.get("parties_uncovered")
    status = values.get("release_status")
    if isinstance(n, bool) or not isinstance(n, (int, float)) or n < 0:
        return None
    if status not in ("scheduled", "on_hold"):
        return None
    return (n > 0) and (status == "scheduled")


def self_check(values, doc_text):
    """The NO-GOLD consistency check: does the reply agree with ITSELF, and does the party it
    names actually exist in the package?

    Three things, none of which needs a label, so a forker can run this over packages nobody has
    scored:

      `party_agrees`  -- first_gap_party is null exactly when parties_uncovered is 0
      `reason_agrees` -- first_gap_reason is 'none' exactly when parties_uncovered is 0
      `party_exists`  -- when a party IS named, the package actually lists it

    ⚠︎ IT IS A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL, and it is blind to the case that matters
    most: a reply that applies the coverage rule wrongly but consistently -- calling a covered
    party uncovered and then naming that same party and a plausible reason -- passes all three.
    Only gold catches that, which is why the confusion matrices in evals/judge.py are the graded
    figures and this is reported beside them.

    Returns a dict of three booleans, each None when the reply did not carry what the check needs.
    """
    n = values.get("parties_uncovered")
    party = values.get("first_gap_party")
    reason = values.get("first_gap_reason")
    numeric = (not isinstance(n, bool)) and isinstance(n, (int, float)) and n >= 0

    out = {"party_agrees": None, "reason_agrees": None, "party_exists": None}
    if numeric:
        out["party_agrees"] = (party in (None, "")) == (n == 0)
        if reason in GAP_REASONS or reason == "none":
            out["reason_agrees"] = (reason == "none") == (n == 0)
    if party:
        out["party_exists"] = segment.locate(doc_text, party) is not None
    return out


def _locate(doc_text, secs, field_name, value):
    """Where in the package this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED FOR THE REASON EVERY SIBLING KIT SCOPES IT, WHICH BITES HARDER HERE: a package
    carries four or five money amounts, four or five dates and four or five company names in one
    section, and an unscoped document-wide search can cite the wrong party's line for a value
    that is genuinely correct.

    ⚑ THE THOUSANDS-SEPARATOR FALLBACK IS A DOCUMENTED NORMALISATION, NOT A GUESS. The model is
    asked for `payment_amount_usd` as a bare number and the package writes it as `175,244.74 USD`,
    so a literal search for `175244.74` finds nothing and the field would ship spanless on every
    single package. The fallback tries exactly one alternative spelling -- the same number with
    thousands separators and two decimals -- and nothing else.
    """
    tries = [value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        tries.append(format(float(value), ",.2f"))
    for v in tries:
        for s in selector.for_field(secs, field_name):
            hit = segment.locate(s["text"], v)
            if hit:
                return s["start"] + hit[0], s["start"] + hit[1]
    for v in tries:
        hit = segment.locate(doc_text, v)
        if hit:
            return hit
    return None


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one payment package. `complete` is injectable so the eval
    harness, the app and tests all drive the same code path against a stub provider."""
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    values = P.parse(raw, fields)
    parsed_ok = bool(values) and any(v is not None for v in values.values())

    out = {}
    for f in fields:
        name = f["name"]
        v = values.get(name)
        if v in ("", "null", "None"):
            v = None
        span_ok = spannable(f)
        span = _locate(doc_text, secs, name, v) if (v is not None and span_ok) else None
        out[name] = {
            "value": v,
            "spannable": span_ok,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}

    return {
        "fields": out,
        "needs_hold": compute(flat),
        "self_check": self_check(flat, doc_text),
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
