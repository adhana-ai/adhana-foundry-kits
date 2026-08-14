"""The corpus: sixty one-page business documents, each emitted twice — clean, and degraded.

⚑ WHY THIS IS SELF-AUTHORED, AND WHY THAT IS NOT A COMPROMISE.

Every other corpus on this site is real public text, and that is the right default. It cannot be
the default here. This kit needs the SAME page in two conditions with one ground truth attached to
both, and no public corpus ships that pair. Real scanned enterprise documents cannot be published
at all — third-party, usually confidential, licences that do not permit redistribution — which is
the one legal landmine a public repo has. Writing the documents ourselves removes the argument
entirely and is also the only way the degraded half can be held to a known answer: we know what the
page said before it was damaged, because we wrote it.

⚠︎ AND IT IS THE THING TO BE MOST HONEST ABOUT. The degraded half is a MODEL of scanner and OCR
damage, not the output of a real scanner. Every error class below is one that OCR demonstrably
makes, and the rates are set to land in the range a mediocre scan produces — but this is a
simulation, and no number this kit publishes should be read as "measured against real scans". That
claim belongs in `could_not_verify`, and it is there.

⚑ BYTE-IDENTICAL ON EVERY REBUILD. One `random.Random(SEED)` threaded through, no clock, no dict
iteration order that varies, no set iteration. A forker who runs tools/build_corpus.py gets the
corpus this kit's published numbers were measured on, or the numbers mean nothing.
"""
import random

SEED = 20260814
N_DOCS = 60

CURRENCIES = ["USD", "EUR", "GBP"]

# The four document kinds. Generic on purpose: an invoice is an invoice in every industry, which is
# what keeps the kit forkable. A vertical ("insurance claim forms") would narrow it to people
# already in that industry, which is the opposite of the point.
KINDS = ["INVOICE", "PURCHASE ORDER", "REMITTANCE ADVICE", "STATEMENT OF ACCOUNT"]

VENDORS = [
    "Northwind Supply Co", "Aldergate Logistics", "Purely Print Ltd", "Bramble & Fitch",
    "Castleford Metals", "Danforth Paper", "Eastvale Components", "Fairhaven Textiles",
    "Granite Row Services", "Harlow Instruments", "Ironbridge Freight", "Juniper Packaging",
    "Kestrel Fasteners", "Lockwood Chemicals", "Meridian Office", "Norbury Tooling",
    "Oakhurst Electrical", "Pemberton Glass", "Quarry Lane Stone", "Redgrave Plastics",
]

# ⚑ LABEL WORDING VARIES BY DOCUMENT, AND THAT IS THE POINT, NOT DECORATION.
# "Inconsistent enterprise documents" is half the problem being measured. A rules baseline that
# anchors on one spelling of a label looks excellent on a corpus that always spells it the same
# way, and that flattering number is exactly what this kit exists to puncture. Each document draws
# its own label for each field.
LABELS = {
    # Kind-NEUTRAL wordings. "Invoice No." was in this list and landed on purchase orders and
    # statements, which is not inconsistency, it is a document contradicting itself. The variance
    # being modelled is that two suppliers label the same field differently, not that one supplier
    # calls a purchase order an invoice.
    "doc_number": ["Document Number", "Ref No.", "Number:", "Doc No.", "Reference Number"],
    "doc_date":   ["Date", "Issue Date", "Dated", "Document Date", "Date of Issue"],
    "total":      ["Total Due", "Amount Due", "Total", "Balance Due", "Grand Total"],
    "counterparty": ["From", "Supplier", "Vendor", "Issued By", "Remit To"],
    "reference":  ["PO Number", "Your Ref", "Order Ref", "Purchase Order", "Customer Ref"],
}

ITEMS = [
    "Steel brackets, 40mm", "Copier paper A4, 80gsm", "Cable ties, 200mm", "Nitrile gloves, L",
    "Packing tape, clear", "Hex bolts M8", "Toner cartridge, black", "Safety goggles",
    "Pallet wrap, 500mm", "Floor sealant, 5L", "Label rolls, 100x50", "Drill bits, HSS set",
]


def _money(rng):
    return round(rng.uniform(120, 48000), 2)


def _date(rng):
    return "%04d-%02d-%02d" % (2026, rng.randint(1, 8), rng.randint(1, 28))


def make_documents():
    """Sixty documents and their ground truth. Pure function of SEED."""
    rng = random.Random(SEED)
    docs = []
    for i in range(N_DOCS):
        kind = KINDS[i % len(KINDS)]
        vendor = VENDORS[rng.randrange(len(VENDORS))]
        currency = CURRENCIES[rng.randrange(len(CURRENCIES))]
        # The prefix follows the document KIND. Drawn at random it produced a purchase order
        # numbered RA-78347, which is not messy-in-the-interesting-sense, just careless — and a
        # reader who spots one careless detail is right to distrust the rest of the corpus.
        number = "%s-%05d" % ({"INVOICE": "INV", "PURCHASE ORDER": "PO",
                               "REMITTANCE ADVICE": "RA", "STATEMENT OF ACCOUNT": "STM"}[kind],
                              rng.randint(1000, 99999))
        date = _date(rng)
        total = _money(rng)

        # ⚑ A THIRD OF DOCUMENTS OMIT THE REFERENCE, ON PURPOSE.
        # Without absent fields the only thing measurable is whether a value was read correctly,
        # and the more expensive real-world failure is inventing one that was never on the page.
        # These are the refusal cells: the right answer is "not stated", and a system that fills
        # them in is hallucinating. Degradation makes that worse, which is the interesting part.
        has_ref = (i % 3) != 0
        reference = "PO-%06d" % rng.randint(100000, 999999) if has_ref else None

        lab = {k: v[rng.randrange(len(v))] for k, v in sorted(LABELS.items())}
        lines = []
        lines.append(vendor.upper())
        lines.append("%s  |  %s" % (rng.choice(["Trade Counter", "Head Office", "Depot 4"]),
                                    rng.choice(["Bristol", "Leeds", "Antwerp", "Cork"])))
        lines.append("")
        lines.append(kind)
        lines.append("")
        lines.append("%s: %s" % (lab["doc_number"], number))
        lines.append("%s: %s" % (lab["doc_date"], date))
        if has_ref:
            lines.append("%s: %s" % (lab["reference"], reference))
        lines.append("%s: %s" % (lab["counterparty"], vendor))
        lines.append("")
        lines.append("Description                         Qty      Line total")
        sub = 0.0
        for _ in range(rng.randint(2, 5)):
            item = ITEMS[rng.randrange(len(ITEMS))]
            qty = rng.randint(1, 40)
            amt = round(rng.uniform(20, 4000), 2)
            sub += amt
            lines.append("%-35s %4d %14s" % (item[:35], qty, "%.2f" % amt))
        lines.append("")
        lines.append("%-40s %14s" % ("Subtotal", "%.2f" % round(sub, 2)))
        lines.append("%-40s %14s" % ("Tax", "%.2f" % round(total - sub if total > sub else 0.0, 2)))
        lines.append("%-40s %14s" % ("%s (%s)" % (lab["total"], currency), "%.2f" % total))
        lines.append("")
        lines.append("Payment terms: %d days from date of issue." % rng.choice([14, 30, 45, 60]))
        lines.append("Registered in England. VAT %d." % rng.randint(100000000, 999999999))

        docs.append({
            "doc_id": "d%03d" % i,
            "kind": kind,
            "clean": "\n".join(lines),
            "gold": {
                "doc_number": number,
                "doc_date": date,
                "total_amount": "%.2f" % total,
                "currency": currency,
                "counterparty": vendor,
                "reference": reference,      # None means NOT STATED — a refusal cell
            },
        })
    return docs


# ─── THE DEGRADATION MODEL ───────────────────────────────────────────────────────────────────────
# Every class below is one OCR demonstrably makes. They are applied per-character or per-line at
# the rates named, and the rates together land around a 6-8% character error rate, which is where a
# mediocre scan of a clean printed page sits. Turn any of them off and the gap this kit measures
# gets smaller; that is the knob a forker will want first.

CONFUSABLE = {
    "l": "1", "1": "l", "I": "l", "O": "0", "0": "O", "S": "5", "5": "S",
    "B": "8", "8": "B", "G": "6", "Z": "2", "2": "Z", "g": "9", "q": "9",
}
LIGATURE = [("rn", "m"), ("m", "rn"), ("cl", "d"), ("vv", "w"), ("ii", "n")]


def degrade(text, rng):
    """One clean document -> the same document as a mediocre scan would hand it back."""
    lines = text.split("\n")
    out = []
    for line in lines:
        # Column bleed: a wide line occasionally picks up a fragment of its neighbour. This is what
        # destroys label-anchored rules — the label and its value stop being on the same line.
        if line.strip() and rng.random() < 0.06:
            line = line[:len(line) // 2] + "  " + rng.choice(["|", "l", ":", "~"]) + " " + \
                   line[len(line) // 2:]
        chars = []
        for ch in line:
            r = rng.random()
            if ch in CONFUSABLE and r < 0.055:
                chars.append(CONFUSABLE[ch])            # glyph confusion, the classic OCR error
            elif ch == " " and r < 0.035:
                continue                                 # space swallowed — words run together
            elif ch.isalpha() and r < 0.012:
                chars.append(ch + " ")                   # space inserted mid-word
            elif ch in ".,:;" and r < 0.10:
                continue                                 # punctuation dropped
            elif ch.isalnum() and r < 0.008:
                chars.append(rng.choice("|~^*"))         # speckle read as a glyph
            else:
                chars.append(ch)
        line = "".join(chars)
        for a, b in LIGATURE:
            if a in line and rng.random() < 0.18:
                line = line.replace(a, b, 1)
        out.append(line.rstrip())

    # Header/footer intrusion: the scanner's page furniture lands in the middle of the body. Real,
    # common, and it moves text that a rules baseline is counting on being in a fixed place.
    if len(out) > 6 and rng.random() < 0.45:
        pos = rng.randrange(3, len(out) - 1)
        out.insert(pos, rng.choice([
            "Page 1 of 1", "-- scanned copy --", "CONFIDENTIAL",
            "Doc ref: %d" % rng.randint(10000, 99999)]))

    # Line joins: the de-hyphenator fails and two lines become one, or one becomes two.
    joined = []
    i = 0
    while i < len(out):
        if i + 1 < len(out) and out[i].strip() and out[i + 1].strip() and rng.random() < 0.07:
            joined.append(out[i] + " " + out[i + 1].strip())
            i += 2
        else:
            joined.append(out[i])
            i += 1
    return "\n".join(joined)


def build():
    """Both conditions for every document, from one seeded stream."""
    docs = make_documents()
    rng = random.Random(SEED + 1)
    for d in docs:
        d["messy"] = degrade(d["clean"], rng)
    return docs
