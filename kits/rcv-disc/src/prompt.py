"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER CASE, NOT PER LINE. A case's 2-4 line items (PO/BOL/receiving quantities for each
SKU) and its one carrier exception note are all sent together, and the model finds the discrepant
line, proposes a liable party, and drafts the notice in a single pass -- the same discipline
data-reconcile's one-call-per-order and fin-payrun's one-call-per-invoice both follow: the raw
record is the shared payload, batching every part of the answer into one call is what keeps this
kit from re-sending the same case once per question asked about it.

⚠︎ A CARRIER EXCEPTION ON THE CASE IS NOT, BY ITSELF, EVIDENCE ABOUT THE DISCREPANT LINE. This is
the failure mode the eval exists to catch, and it is said to the model in as many words rather than
left for it to discover: an exception note can be real, on file, and about a completely different
SKU than the one that is actually short. Reading "an exception exists" as "the carrier did it"
without checking which SKU the note names produces a liable-party call the evidence does not
support -- the exact defect `evals/scoring.py`'s `wrong_sku_exception_misread` measures.

⚠︎ THE FOURTH VALUE IS THE ONE THAT MATTERS MOST. `insufficient_evidence` exists because the three
quantities sometimes disagree in a shape none of the other three rules resolve cleanly -- an
apparent over-shipment, or more than one quantity off at once. A model that forces a confident call
onto a case like that manufactures a liable party the documents do not support; the safe answer is
to say so, the same way data-reconcile's `unverifiable` and fin-payrun's precedence rule both refuse
to let a downstream-looking field stand in for a clean answer. Silence in the evidence is never a
reason to guess.

⚠︎ THIS KIT NEVER ISSUES A CHARGEBACK OR A CREDIT, AND IT NEVER MAKES THE FINAL LIABILITY CALL.
The reply proposes a probable liable party and its documentary basis for receiving/AP to confirm --
see src/resolve.py's module docstring for where that boundary is enforced in code, not just here.
"""
import json

LIABLE_PARTIES = ("vendor", "carrier", "internal", "insufficient_evidence")
DOCS = ("po", "bol", "received")

LIABLE_MEANINGS = {
    "vendor": "the BOL states LESS than the PO ordered, and receiving recorded exactly what the "
             "BOL says was shipped. The carrier delivered everything it was given; the vendor "
             "gave it less than the PO called for. Cite PO vs BOL.",
    "carrier": "the BOL states the full PO quantity was shipped, receiving recorded less than "
              "that, AND the carrier's own exception note names this exact SKU. The carrier "
              "picked up the full order and delivered less, and its own paperwork corroborates a "
              "transit loss or damage for this line. Cite BOL vs Received.",
    "internal": "the BOL states the full PO quantity was shipped and receiving recorded less "
               "than that, but nothing corroborates a transit loss for THIS line -- either there "
               "is no carrier exception on file at all, or the exception on file names a "
               "DIFFERENT SKU than this one. It looks like a transit-loss pattern, but nothing on "
               "file backs it for this line; the likely explanation is a dock miscount, not a "
               "proven transit loss. Cite BOL vs Received.",
    "insufficient_evidence": "the three quantities disagree in a shape none of the other three "
                            "calls resolve cleanly -- most often the BOL and receiving AGREE with "
                            "each other but both disagree with the PO (an apparent "
                            "over-shipment, not a shortfall), or more than one of the three "
                            "quantities is off at once. There is no clean documentary basis for a "
                            "liability call. Cite PO vs Received.",
}

_MEANINGS_TXT = "".join("  %-22s %s\n" % (name, LIABLE_MEANINGS[name]) for name in LIABLE_PARTIES)

SYSTEM = (
    "You build a receiving-discrepancy case file for one case and propose a probable liable "
    "party, for receiving/AP to confirm before any chargeback or credit is issued. You are given "
    "every SKU line on the case -- each with the quantity the PO ordered, the quantity the BOL "
    "states was shipped, and the quantity receiving actually scanned -- plus one carrier "
    "exception note, which is either absent or names ONE specific SKU.\n\n"
    "Exactly one line on the case is genuinely discrepant: its PO, BOL and receiving quantities "
    "do not all agree. Every other line is clean (all three quantities equal) -- find the "
    "discrepant line among them, do not assume it is the first one listed.\n\n"
    "THE FOUR VALUES FOR liable_party, EXACTLY ONE APPLIES\n" + _MEANINGS_TXT + "\n"
    "⚠︎ A CARRIER EXCEPTION EXISTING ON THE CASE IS NOT, BY ITSELF, EVIDENCE THAT THE CARRIER IS "
    "LIABLE FOR THIS LINE. Check whether the exception names the SAME SKU as the discrepant line. "
    "An exception about a different SKU is a real note about a different problem -- it does not "
    "excuse this one, and calling the carrier liable on its strength alone is exactly the mistake "
    "this task exists to catch.\n\n"
    "The notice you draft must name the discrepant SKU and state which two of the three "
    "quantities (po, bol, received) disagree, their values, and the delta between them -- e.g. "
    "\"BOL states 240 units shipped; receiving recorded 210 units, a shortfall of 30.\" Use "
    "whichever pair the liable_party value above says to cite. delta is the absolute difference "
    "between qty_a and qty_b, never signed.\n\n"
    "You never issue a chargeback or a credit yourself, and you never make the final liability "
    "determination -- you propose a probable liable party and its documentary basis for "
    "receiving/AP to confirm and act on."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _case_block(case):
    lines = "\n".join(
        "  %-10s  PO %-5s BOL %-5s Received %-5s"
        % (l["sku"], l["po_qty"], l["bol_qty"], l["received_qty"])
        for l in case["lines"]
    )
    exc = case.get("carrier_exception") or "none on file"
    return (
        "CASE %s (PO %s, carrier %s)\n"
        "Lines:\n%s\n"
        "Carrier exception: %s\n"
        % (case["case_id"], case["po_number"], case["carrier_name"], lines, exc)
    )


def build(case, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    case_block = _case_block(case)
    user = (
        "Build the case file for the case below and propose a probable liable party.\n\n"
        "Return a JSON object with exactly these keys: \"liable_party\" (one of: %s), "
        "\"discrepant_sku\" (the SKU of the one discrepant line), \"doc_a\" and \"doc_b\" (the "
        "two of \"po\", \"bol\", \"received\" that disagree, per the liable_party value's citation "
        "rule above), \"qty_a\" and \"qty_b\" (their quantities), \"delta\" (the absolute "
        "difference between qty_a and qty_b), \"notice_text\" (the drafted notice, one or two "
        "sentences).\n\n%s" % (", ".join(LIABLE_PARTIES), case_block)
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "case", "text": case_block},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the field set out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields an all-None result -- read as "this call produced no
    answer", never as evidence about the case -- never a regex fallback that scrapes a
    plausible-looking verdict out of raw text. That would silently turn a broken call into a
    mediocre resolver.
    """
    empty = {"liable_party": None, "discrepant_sku": None, "doc_a": None, "doc_b": None,
             "qty_a": None, "qty_b": None, "delta": None, "notice_text": None}
    if not raw:
        return empty
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return empty
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return empty

    liable = str(obj.get("liable_party", "") or "").strip().lower().replace(" ", "_").replace("-", "_")
    if liable not in LIABLE_PARTIES:
        liable = None

    sku = obj.get("discrepant_sku")
    sku = str(sku).strip() if sku else None

    def _doc(v):
        v = str(v or "").strip().lower()
        return v if v in DOCS else None

    doc_a, doc_b = _doc(obj.get("doc_a")), _doc(obj.get("doc_b"))

    def _num(v):
        return v if isinstance(v, (int, float)) else None

    qty_a, qty_b, delta = _num(obj.get("qty_a")), _num(obj.get("qty_b")), _num(obj.get("delta"))
    notice = obj.get("notice_text")
    notice = str(notice) if notice else None

    return {"liable_party": liable, "discrepant_sku": sku, "doc_a": doc_a, "doc_b": doc_b,
           "qty_a": qty_a, "qty_b": qty_b, "delta": delta, "notice_text": notice}
