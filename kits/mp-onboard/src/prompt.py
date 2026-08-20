"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER SELLER APPLICATION, ALL SEVEN FIELD PAIRS IN IT. The model reads the applicant's
declared business identity, banking details and owner identity together with the three submitted
verification documents (business registration, bank letter, government ID) and the applicant's own
submission note, and fills one small field set in one call: a match/mismatch/mismatch_explained
flag for each of the seven declared-vs-document field pairs, plus a short drafted summary for the
verification analyst. It never outputs an approve/deny/escalate decision -- see the guardrail below.

⚠︎ THIS KIT NEVER DECIDES THE APPLICATION. `requires_ap_review` doesn't exist here on purpose --
there is no boolean anywhere in this reply shape that stands in for an approve/deny/escalate call.
The model extracts and cross-checks; a verification analyst decides. See src/onboard.py's module
docstring for where that boundary is enforced in code, not just in this prompt.

⚠︎ THE EXPENSIVE DIRECTION, NAMED TO THE MODEL. An application where six of seven fields match
cleanly and only bank_routing_number disagrees is not "probably fine" -- see tools/build_corpus.py
for exactly how and how often that pattern is planted. This is the one failure this kit exists to
catch, named in the system prompt in as many words: a mismatched banking detail on an
otherwise-clean application is not evidence the application is clean, it is the pattern a
fraudulent one produces.

⚠︎ THE OTHER DIRECTION IS NAMED TOO. mismatch_explained is not "there was some note attached" --
it is "the note specifically and genuinely accounts for THIS field's discrepancy". A generic or
unrelated submission_note does not explain a banking mismatch, a name mismatch, or an address
mismatch, and reading it as if it does is exactly the over-explaining failure evals/scoring.py
scores on its own, distinct from the missed-mismatch direction above.
"""
import json

FIELDS = (
    "business_name",
    "business_address",
    "tax_id",
    "bank_account_name",
    "bank_routing_number",
    "owner_name",
    "owner_address",
)

FLAGS = ("match", "mismatch", "mismatch_explained")

# Declared field -> where the corresponding value lives on the submitted verification documents.
# Stated here once so src/prompt.py, src/onboard.py, evals/scoring.py and tools/build_corpus.py
# all read the same pairing rather than each hard-coding it.
FIELD_SOURCES = {
    "business_name": "business_registration.legal_name",
    "business_address": "business_registration.registered_address",
    "tax_id": "business_registration.tax_id",
    "bank_account_name": "bank_letter.account_holder_name",
    "bank_routing_number": "bank_letter.routing_number",
    "owner_name": "id_document.full_name",
    "owner_address": "id_document.address",
}

FIELD_MEANINGS = {
    "business_name": "declared business_name against the business registration document's "
                     "legal_name",
    "business_address": "declared business_address against the business registration document's "
                        "registered_address",
    "tax_id": "declared tax_id against the business registration document's own tax_id",
    "bank_account_name": "declared bank_account_name against the bank letter's "
                         "account_holder_name",
    "bank_routing_number": "declared bank_routing_number against the bank letter's "
                           "routing_number",
    "owner_name": "declared owner_name against the government ID document's full_name",
    "owner_address": "declared owner_address against the government ID document's address",
}

FLAG_MEANINGS = {
    "match": "the declared value and the document value agree",
    "mismatch": "they disagree, and nothing in submission_note explains why",
    "mismatch_explained": "they disagree, AND submission_note specifically and genuinely "
                          "accounts for THAT EXACT field's discrepancy -- not a generic note, "
                          "not a note about a different field",
}

_FIELDS_TXT = "".join("  %-20s %s\n" % (f, FIELD_MEANINGS[f]) for f in FIELDS)
_FLAGS_TXT = "".join("  %-20s %s\n" % (v, FLAG_MEANINGS[v]) for v in FLAGS)

SYSTEM = (
    "You extract and cross-check a third-party seller's onboarding application. You are given "
    "the applicant's declared business identity, banking details and owner identity; the "
    "business registration document; the bank verification letter; the government ID document; "
    "and the applicant's own submission note (which may be empty). All three documents are "
    "already extracted to clean text -- you are not reading images.\n\n"
    "YOU NEVER APPROVE, DENY, OR ESCALATE THIS APPLICATION, AND YOU NEVER AUTO-CLEAR A FLAGGED "
    "INCONSISTENCY, EVEN ONE THAT LOOKS MINOR. That decision belongs to a verification analyst. "
    "Your only job is to extract each declared field, compare it against the matching document "
    "field, and flag every inconsistency -- every mismatch and every mismatch_explained stays in "
    "your output; there is no field you drop because it seems small.\n\n"
    "THE SEVEN FIELD PAIRS, EACH FLAGGED INDEPENDENTLY\n" + _FIELDS_TXT + "\n"
    "FOR EACH FIELD, EXACTLY ONE OF THREE FLAGS\n" + _FLAGS_TXT + "\n"
    "⚠︎ A SINGLE MISMATCH ON AN OTHERWISE-CLEAN APPLICATION IS NOT A REASON TO SOFTEN IT. An "
    "application where six of seven fields match cleanly and only bank_routing_number disagrees "
    "is not \"probably fine\" -- a mismatched banking detail on an application that looks clean "
    "everywhere else is the exact pattern a fraudulent submission produces. Flag it exactly as "
    "you would flag it on a messier application; do not let five or six clean fields talk you "
    "out of the one that isn't.\n\n"
    "⚠︎ NEVER CALL A FIELD mismatch_explained UNLESS submission_note SPECIFICALLY NAMES THAT "
    "FIELD'S DISCREPANCY. An empty note, a generic note (\"please process quickly\"), or a note "
    "that explains a different field does not explain this one -- when in doubt, the correct "
    "flag is mismatch, not mismatch_explained. A genuinely explained discrepancy IS a real, "
    "legitimate outcome -- \"recently changed business address, registration update pending\" "
    "does explain a business_address mismatch -- but the note has to actually say so for this "
    "field, not merely exist.\n\n"
    "Return a JSON object with exactly these keys: business_name, business_address, tax_id, "
    "bank_account_name, bank_routing_number, owner_name, owner_address (each one of: match, "
    "mismatch, mismatch_explained), and summary (one or two sentences drafted for the "
    "verification analyst, naming which fields you flagged and why -- never a decision to "
    "approve, deny, or escalate the application)."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _doc_block(app):
    d, br, bl, idd = app["declared"], app["business_registration"], app["bank_letter"], \
        app["id_document"]
    note = app.get("submission_note") or ""
    return (
        "APPLICATION %s\n"
        "DECLARED ON THE APPLICATION FORM\n"
        "  business_name: %s\n"
        "  business_address: %s\n"
        "  tax_id: %s\n"
        "  bank_account_name: %s\n"
        "  bank_routing_number: %s\n"
        "  owner_name: %s\n"
        "  owner_address: %s\n"
        "BUSINESS REGISTRATION DOCUMENT\n"
        "  legal_name: %s\n"
        "  registered_address: %s\n"
        "  tax_id: %s\n"
        "BANK VERIFICATION LETTER\n"
        "  account_holder_name: %s\n"
        "  routing_number: %s\n"
        "GOVERNMENT ID DOCUMENT\n"
        "  full_name: %s\n"
        "  address: %s\n"
        "SUBMISSION NOTE: %s\n"
        % (app["application_id"],
           d["business_name"], d["business_address"], d["tax_id"], d["bank_account_name"],
           d["bank_routing_number"], d["owner_name"], d["owner_address"],
           br["legal_name"], br["registered_address"], br["tax_id"],
           bl["account_holder_name"], bl["routing_number"],
           idd["full_name"], idd["address"],
           note if note else "(none provided)")
    )


def build(app, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    doc_block = _doc_block(app)
    user = (
        "Cross-check the application below field by field and draft a summary for the "
        "verification analyst.\n\n"
        "Return a JSON object with exactly eight keys: %s (each one of: %s), and \"summary\" "
        "(the drafted note, one or two sentences).\n\n%s"
        % (", ".join(FIELDS), ", ".join(FLAGS), doc_block)
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "application", "text": doc_block},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the field set out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields an all-None result -- read as "this call produced no
    answer", never as evidence about the application -- never a regex fallback that scrapes a
    plausible-looking flag out of raw text. That would silently turn a broken call into a
    mediocre cross-checker.
    """
    out = {f: None for f in FIELDS}
    out["summary"] = None
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
    for f in FIELDS:
        v = str(obj.get(f, "") or "").strip().lower().replace(" ", "_").replace("-", "_")
        if v in FLAGS:
            out[f] = v
    summary = obj.get("summary")
    out["summary"] = summary if isinstance(summary, str) else None
    return out
