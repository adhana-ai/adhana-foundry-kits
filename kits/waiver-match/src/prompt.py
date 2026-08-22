"""Assemble the extraction prompt. One prompt per lien-waiver payment package, all eleven fields
in it.

⚠︎ THE GUARDED FIELDS OF THIS KIT ARE `parties_uncovered`, `first_gap_party` AND
`first_gap_reason`, AND ALL THREE COME OUT OF ONE FIVE-CONDITION RULE WITH A PRIORITY ORDER. The
rule is stated in full rather than left for the model to infer, because the measurable failures
this kit exists to catch are all failures of ORDER or of SCOPE, not of arithmetic:

  1. A PRELIMINARY NOTICE DATED AFTER THE WAIVER WAS SIGNED OUTRANKS EVERYTHING BELOW IT. The
     waiver can be unconditional, for the full amount, covering the whole period -- and it was
     signed before the claim it would have to reach was asserted. Every check a fast reader runs
     says covered.
  2. A FINAL WAIVER HAS NO THROUGH-DATE AND CAN NEVER BE SHORT ON PERIOD. It reaches all work
     through completion. A reader mechanically comparing through-dates finds "n/a" and calls it
     a gap.
  3. PERIOD OUTRANKS AMOUNT. A waiver for twice the amount due whose through-date stops inside
     the period is period_short, not covered and not amount_short.
  4. A JOINT CHECK CLEARS ON ISSUE. Both payees negotiate it, so a conditional waiver on a
     joint-check party is already spent even when the package says the prior payment has NOT
     cleared. This is the one case where the package-level answer is not the answer.
  5. THE COORDINATOR NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds settled does not
     mean the waiver file is complete, and a note that sounds worried does not mean it is not --
     only the party blocks, the period-through date and the prior-payment answer decide.

⚑ ONE CALL PER PACKAGE, NOT ONE PER PARTY -- the question is asked ACROSS parties (how many are
uncovered, and which is the first), so the parties have to arrive together. It is also the same
shape as every sibling extraction kit here.

⚠︎ NOTHING IN THIS PROMPT DETERMINES LIEN RIGHTS. It asks the model to assemble a coverage
picture and name where it is incomplete. Releasing the payment is a person's decision.
"""
import json

SYSTEM = (
    "You read a construction progress-payment package and report which parties on it are covered "
    "by a lien waiver and which are not. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the package does not state a field, return null for it. Do not infer it and do not "
    "use what you know about the world.\n"
    "2. `parties_uncovered`, `first_gap_party` and `first_gap_reason` are decided by applying ONE "
    "COVERAGE RULE to EACH party under `Waiver Coverage`, in document order, never by how the "
    "coordinator note reads. For each party, work through these five conditions IN ORDER and stop "
    "at the FIRST one that is true:\n"
    "   a. `no_waiver_on_file` -- the party's `Waiver on file` line says none.\n"
    "   b. `notice_after_waiver` -- the party has a `Preliminary notice on file` date AND it is "
    "LATER than the `Waiver signed` date. The waiver was signed before the claim was asserted, so "
    "it does not reach it. THIS OUTRANKS EVERYTHING BELOW -- it is true even when the waiver is "
    "unconditional, is for the full amount, and covers the whole period.\n"
    "   c. `period_short` -- the party has a PROGRESS waiver (conditional progress or "
    "unconditional progress) whose `Waiver covers work through` date is EARLIER than the "
    "package's `Period Through` date. A FINAL waiver (conditional final or unconditional final) "
    "has NO through-date -- it covers all work through completion -- so a final waiver is NEVER "
    "`period_short`, and its \"n/a\" through-date is not a gap.\n"
    "   d. `amount_short` -- the `Waiver amount` is LESS THAN that party's `Amount due this "
    "application`.\n"
    "   e. `conditional_stale` -- the waiver is CONDITIONAL (conditional progress or conditional "
    "final) AND something has already cleared against it: either the package's `Prior Payment "
    "Cleared` is yes, OR that party's `Joint check arrangement` is yes. A joint check is "
    "negotiated by both payees, so it clears on issue -- a conditional waiver on a joint-check "
    "party is stale EVEN WHEN the package says the prior payment has not cleared.\n"
    "   A party for which none of the five is true is COVERED.\n"
    "3. THE ORDER IS PART OF THE RULE. More than one condition can be true of the same party, and "
    "only the FIRST one in the list above is reported. A waiver for twice the amount due whose "
    "through-date stops inside the period is `period_short`, not `amount_short`.\n"
    "4. `parties_uncovered` is the COUNT of parties for which any condition fired. "
    "`first_gap_party` is the name of the FIRST such party in document order, and "
    "`first_gap_reason` is that party's own first-firing condition. When every party is covered, "
    "return 0, null and 'none' respectively.\n"
    "5. THE COORDINATOR NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT COVERAGE. A note that sounds "
    "settled does NOT mean every party is covered, and a note that sounds worried does NOT mean "
    "one is not. The party blocks, the period-through date and the prior-payment answer decide; "
    "the note is the coordinator's own remark and may disagree with them.\n"
    "6. Copy values verbatim from the package wherever possible, and report "
    "payment_amount_usd as a bare number with no currency symbol, no thousands separators and no "
    "unit. Report first_gap_party as the party's name exactly as the package writes it, without "
    "the \"Party N: \" prefix.\n"
    "7. Use the exact allowed value for a field that lists them.\n"
    "8. Return every field named in the schema, even when the answer is null.\n"
    "\n"
    "You are assembling evidence for a person, not authorising anything. Nothing you return "
    "releases a payment or decides anybody's lien rights."
)


def field_schema(fields):
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    names = [f["name"] for f in fields]
    wanted, seen = [], set()
    for name in names:
        for s in selector.for_field(secs, name):
            if s["start"] not in seen:
                seen.add(s["start"])
                wanted.append(s)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = field_schema(fields)
    user = ("Extract these fields:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the package does not state.\n\n"
            "PROGRESS PAYMENT PACKAGE\n------------------------\n%s\n"
            % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "package sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return {f["name"]: obj.get(f["name"]) for f in fields}
