#!/usr/bin/env python3
"""The free floor: label-anchored rules over whatever text layer you were handed. No model, $0.00.

    python3 evals/baseline.py clean
    python3 evals/baseline.py messy

⚑ WHY THIS IS THE RIGHT FLOOR FOR THIS KIT. The question is not "can a model extract fields" —
docs-extract already answered that. It is "how much does extraction degrade when the input is
messy", and that question is only meaningful against something whose degradation you can predict.
Rules are that something: they anchor on a label and a shape, and OCR damage attacks exactly those
two things. If the model degrades no better than the rules do, the model is not buying you
robustness and this kit says so.

⚠︎ THIS IS A REAL BASELINE, NOT A STRAW MAN. It knows every label spelling the corpus uses, it
tolerates a missing colon, it accepts the confusable-glyph forms of digits, and it takes the LAST
total on the page rather than the first number it sees. A floor built to lose proves nothing — the
comparison is only worth publishing if the cheap thing was given a fair run.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from evals.score import score_all, load_gold, load_fields  # noqa: E402

# Every label wording the corpus uses, plus the ones a forker's documents are likely to use. The
# baseline is allowed to know these: a rules extractor in production would be tuned to its own
# document set, and pretending otherwise would understate the floor.
ANCHORS = {
    "doc_number": ["document number", "ref no", "number", "doc no", "reference number",
                   "invoice no", "invoice #"],
    "doc_date": ["date", "issue date", "dated", "document date", "date of issue"],
    "total_amount": ["total due", "amount due", "total", "balance due", "grand total"],
    "counterparty": ["from", "supplier", "vendor", "issued by", "remit to"],
    "reference": ["po number", "your ref", "order ref", "purchase order", "customer ref"],
}

# OCR turns digits into letters and back. The baseline undoes the ones it can, because a rules
# extractor that did not would be a straw man — this is the first thing anyone writes after seeing
# their first scanned page.
UNCONFUSE = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8", "|": "1"})

MONEY = re.compile(r"(\d[\d,]*\.\d{2})")
DATE = re.compile(r"(\d{4})[-/ ](\d{1,2})[-/ ](\d{1,2})")
CODE = re.compile(r"\b([A-Z]{2,4})[-\s]?(\d{4,6})\b")
CCY = re.compile(r"\b(USD|EUR|GBP)\b")


def _label_value(text, names):
    """The text after a label on the same line, tolerating a dropped colon and inserted spaces."""
    for line in text.split("\n"):
        squashed = re.sub(r"\s+", " ", line).strip()
        low = squashed.lower().replace(" ", "")
        for n in names:
            key = n.replace(" ", "")
            if low.startswith(key):
                rest = squashed[len(squashed) - len(squashed):]  # keep original casing
                rest = re.sub(r"^\s*" + re.escape(squashed[:len(n) + 2]), "", squashed)
                rest = squashed.split(":", 1)[1] if ":" in squashed else squashed[len(n):]
                rest = rest.strip(" :|~^")
                if rest:
                    return rest
    return None


def extract(text):
    out = {}
    v = _label_value(text, ANCHORS["doc_number"])
    if v:
        m = CODE.search(v.translate(UNCONFUSE).upper()) or CODE.search(v.upper())
        out["doc_number"] = ("%s-%s" % m.groups()) if m else v.split()[0]
    d = _label_value(text, ANCHORS["doc_date"])
    m = DATE.search((d or "").translate(UNCONFUSE))
    if m:
        out["doc_date"] = "%04d-%02d-%02d" % tuple(int(x) for x in m.groups())
    # The LAST money figure on the page, which is where a total sits. Taking the first would find
    # a line total and score badly for a reason that has nothing to do with legibility.
    monies = MONEY.findall(text.replace(" ", ""))
    if monies:
        out["total_amount"] = monies[-1].replace(",", "")
    m = CCY.search(text)
    if m:
        out["currency"] = m.group(1)
    c = _label_value(text, ANCHORS["counterparty"])
    if c:
        out["counterparty"] = c
    r = _label_value(text, ANCHORS["reference"])
    if r:
        m = CODE.search(r.translate(UNCONFUSE).upper())
        # ⚑ ONLY A WELL-FORMED CODE COUNTS. Returning whatever followed the label is how a rules
        # extractor manufactures hallucinations on a damaged page: the label survives, its value
        # does not, and it confidently reports the noise. The refusal cells exist to catch that.
        if m:
            out["reference"] = "%s-%s" % m.groups()
    return out


def main(condition):
    gold = load_gold(HERE)
    fields = load_fields(HERE)
    t0 = time.time()
    preds, lat = {}, []
    for row in gold:
        p = os.path.join(HERE, "data", "corpus", condition, row["doc_id"] + ".txt")
        s = time.time()
        preds[row["doc_id"]] = extract(open(p, encoding="utf-8").read())
        lat.append(int((time.time() - s) * 1000))
    res = score_all(gold, preds, fields)
    res.update({
        "run_id": "b%s-baseline" % ("000" if condition == "clean" else "001"),
        "stub": False, "model": "rules-baseline", "provider": "none",
        "condition": condition, "documents": len(gold), "failures": [],
        "latency_p50_ms": sorted(lat)[len(lat) // 2], "latency_p95_ms": sorted(lat)[int(len(lat) * .95)],
        "wall_seconds": round(time.time() - t0, 2),
        "input_tokens_total": 0, "output_tokens_total": 0,
    })
    out = os.path.join(HERE, "results", "eval-%s.json" % res["run_id"])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    print("%s  %s  accuracy %.1f%%  refusal %.1f%%  hallucinations %d"
          % (res["run_id"], condition, 100 * res["scores"]["extraction_accuracy"],
             100 * res["scores"]["refusal_accuracy"], res["scores"]["hallucinations"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "clean"))
