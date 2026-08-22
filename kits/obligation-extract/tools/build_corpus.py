#!/usr/bin/env python3
"""Generate synthetic subscription-contract packs and their gold worksheets, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one contract pack per file) and data/gold.jsonl, byte-identical on every
run. Every customer name, order-form reference, line code and fee here is invented. Nothing is
fetched and nothing is licensed from anybody, so the corpus ships under this repo's MIT licence.

⚠︎ NO ACCOUNTING STANDARD IS REPRODUCED, PARAPHRASED OR NAMED. The rule this corpus is built
against is `data/rulebook.json`, which was written for this kit: three stated facts in, two
worksheet calls out. It is illustrative rather than authoritative, and what the kit produces is a
REVIEWER'S WORKSHEET -- never an accounting conclusion, an allocation, a schedule or a journal
entry. See data/SOURCES.md.

⚑ GOLD IS A RULEBOOK LOOKUP, NOT A LABEL SOMEBODY TYPED. `separation` and `pattern` are derived
from the same three values the generator itself decided and then WROTE INTO THE CONTRACT TEXT --
with the same rule the kit publishes everywhere else, src/rulebook.py, which src/prompt.py states
to the model in words and evals/judge.py re-runs over the model's own reply.

⚑ THE FOUR THINGS A CARELESS READER GETS WRONG, and every one is a fixed bucket here:

  priced_silent    -- a line with a FEE OF ITS OWN and nothing said about whether the customer
                      could take it alone. The rulebook answers `not_determined`; a reader who
                      treats a price as evidence of separability answers `distinct`. This is the
                      biggest bucket in the corpus and the failure the kit exists to expose.
  free_but_distinct-- a line the order form prices at NOTHING, which the contract explicitly says
                      the customer may cancel on its own. `distinct`, despite being free. A reader
                      keying on money answers `bundled`.
  free_bundled     -- a line priced at nothing with NOTHING said about separability. `bundled` --
                      and it is one clause away from the case above, which is the point.
  withdrawn_line   -- a line struck by an amendment. Its code, its description AND ITS WHOLE CLAUSE
                      are still printed in the pack; only the order-form row and the notes say it
                      was removed. A reader who works from the clauses lists it as an obligation.

⚑ AND TWO MORE DECOYS THAT ARE NOT ORDER-FORM LINES AT ALL: a professional-services RATE CARD
(a price with no order behind it) and an item CONTINUING under an earlier order form. Both carry
a code in the same format as a real line. Listing either is a phantom obligation on a reviewer's
worksheet, which is the expensive direction on this shape of work.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import rulebook as RB                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 50

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER LINE -- the fix a sibling kit in this
# series had to make after its first generator asked for 40 pct ambiguity and delivered 51. A count
# 1.7 standard deviations off its own design is not a corpus property, it is sampling noise being
# published as one. So every bucket here is a fixed COUNT, dealt by the seeded RNG over the slots
# that can carry it, and asserted at the end.
CONTRACT_SIZES = [(4, 10), (5, 15), (6, 15), (7, 10)]      # (lines per contract, how many)
N_LINES = sum(n * k for n, k in CONTRACT_SIZES)            # 275

SEPARATION_BUCKETS = [
    ("dep_bundled", 45),        # dependency states it is a prerequisite      -> bundled
    ("dep_distinct", 85),       # dependency states it can be taken alone     -> distinct
    ("free_bundled", 40),       # no separate charge, nothing said            -> bundled
    ("priced_silent", 70),      # ITS OWN FEE, nothing said                   -> not_determined
    ("unpriced_silent", 35),    # fee not separately stated, nothing said     -> not_determined
]
TIMING_BUCKETS = [("period", 120), ("event", 85), ("silent", 70)]

# Decoys, dealt across contracts. A contract may carry more than one.
N_WITHDRAWN = 13            # an order-form line struck by an amendment, clause still printed
N_RATE_CARD = 14            # a day rate for work nobody ordered
N_CARRYOVER = 12            # an item continuing under an EARLIER order form

# At least this many `dep_distinct` lines must also be priced at nothing -- the sharpest case in
# the rulebook, where the money column and the answer point opposite ways.
N_FREE_BUT_DISTINCT = 14

SUB = "subscription_platform"
OPTIONAL_TYPES = ("implementation_services", "training_days", "support_tier",
                  "usage_component", "renewal_option", "optional_module")

# Which line types can carry which bucket. A subscription line always has a fee of its own, and
# nothing in a contract is a prerequisite for the platform it is sold with.
CAN_BE_PREREQUISITE = ("implementation_services", "training_days", "optional_module")
CAN_BE_UNPRICED = OPTIONAL_TYPES                       # everything except the platform line
CAN_BE_EVENT = ("implementation_services", "training_days", "renewal_option", "optional_module")

# Invented customer names. Two invented word lists, combined -- no real company, product, brand,
# person or supplier is named anywhere in this kit.
CUST_A = ("Ashvale", "Corwin", "Pellworth", "Larkfield", "Meridian", "Thornbury", "Halstow",
          "Brackenhill", "Quillmere", "Redmarsh", "Silverbeck", "Wraycombe")
CUST_B = ("Analytics", "Logistics", "Health Group", "Retail Group", "Utilities", "Media",
          "Manufacturing", "Financial Services", "Education Trust", "Property Group")
SEGMENTS = ("mid-market", "enterprise", "public sector", "commercial")
EDITIONS = ("standard edition", "professional edition", "enterprise edition")

LABELS = {
    "subscription_platform": ["Platform subscription, %s"],
    "implementation_services": ["Implementation and configuration",
                                "Data migration and configuration",
                                "Onboarding and environment setup"],
    "training_days": ["Administrator training, %d days", "End-user training, %d days",
                      "Enablement workshops, %d days"],
    "support_tier": ["Priority support tier", "Named success manager tier",
                     "Extended-hours support tier"],
    "usage_component": ["Metered API calls above the included allowance",
                        "Additional document processing volume",
                        "Overage storage, charged on consumption"],
    "renewal_option": ["Renewal option for a further term",
                       "Stated price ramp for the second year",
                       "Extension right over the following term"],
    "optional_module": ["Analytics module", "Advanced reporting module",
                        "Regional data-residency module"],
}

# Sentences that STATE a dependency. Nothing else in the pack states one, so a line with no
# sentence from either list here is `silent` -- which is a fact about the paperwork, not a gap.
PREREQ_SENTENCES = {
    "implementation_services": [
        "The platform is not made available to the customer's named users until the "
        "implementation acceptance certificate is signed.",
        "No part of the subscription may be used until this work is accepted in writing.",
    ],
    "training_days": [
        "Named user accounts are not enabled until the training days recorded on this line have "
        "been delivered.",
        "The subscription cannot be brought into use until the training days recorded here have "
        "been delivered.",
    ],
    "optional_module": [
        "The module is supplied only alongside the platform subscription and cannot be taken on "
        "its own.",
        "This module cannot be supplied except together with the subscription line of this order "
        "form.",
    ],
}
SEPARABLE_SENTENCES = [
    "The customer may cancel this line at any time without affecting the remaining lines of this "
    "order form.",
    "The customer may obtain this line from another supplier, and doing so does not affect the "
    "remaining lines of this order form.",
    "This line may be deferred or taken on its own, independently of the rest of this order form.",
]
PERIOD_SENTENCES = [
    "Supplied over the %d-month subscription term, from the service start date.",
    "Provided continuously across the %d-month initial term.",
    "Delivered across the %d-month period beginning on the service start date.",
]
EVENT_SENTENCES = [
    "Complete on signature of the acceptance certificate.",
    "Complete on the date the access credentials are issued to the customer.",
    "Complete when the final scheduled day is delivered and signed off.",
]
TERM_MONTHS = (12, 24, 36, 48)

# Notes that are on every pack. Deal-desk prose, deliberately unhelpful about the calls -- the
# worksheet answer is never derived from it.
CLOSING_NOTES = [
    "Prepared by the deal desk for review. Nothing in this pack has been approved and no schedule "
    "has been opened against it.",
    "Circulated for review only. The controller has not seen this pack and no determination has "
    "been made on any line in it.",
    "Draft pack for the review queue. No allocation, schedule or entry follows from anything "
    "recorded here.",
]


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs. Deterministic."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    while len(out) < n:
        out.append(spec[0][0])
    out = out[:n]
    rng.shuffle(out)
    return out


def _allocate(rng, slots, buckets, eligible):
    """Assign exactly the designed count of every bucket to `slots`, honouring `eligible`.

    ⚑ MOST-CONSTRAINED FIRST, AND EXACT RATHER THAN SAMPLED. `eligible[bucket]` is the set of line
    types that can carry that bucket -- nothing is a prerequisite for the platform it is sold with,
    and a platform line always has a fee of its own. A greedy that ignored the ordering would hand
    every unconstrained bucket to the few slots the constrained ones need, and the composition
    would silently come out short. It raises rather than back-filling: a corpus that cannot be
    built to its own design is a design problem, not something to paper over at generation time.
    """
    # ⚠︎ A BUCKET WITH NO ENTRY IN `eligible` IS UNCONSTRAINED AND MUST SORT LAST, NOT FIRST. The
    # obvious spelling -- `len(eligible.get(name, ()))` -- gives an absent key a width of ZERO, so
    # every unconstrained bucket ran first, ate the slots the narrow ones needed, and the build
    # died claiming a 35-slot bucket had 13 candidates. Absence is "anything", not "nothing".
    def width(name):
        ok = eligible.get(name)
        return len(ok) if ok else 10 ** 6

    order = sorted(buckets, key=lambda b: (width(b[0]), -b[1]))
    free = list(range(len(slots)))
    rng.shuffle(free)
    out = [None] * len(slots)
    for name, count in order:
        ok = eligible.get(name)
        picks = [i for i in free if ok is None or slots[i] in ok][:count]
        if len(picks) < count:
            raise RuntimeError("bucket %r wants %d slots and only %d are eligible"
                               % (name, count, len(picks)))
        for i in picks:
            out[i] = name
        free = [i for i in free if out[i] is None]
    assert not free, "%d slot(s) left unallocated" % len(free)
    return out


def _charge_for(rng, bucket):
    """The fee column that bucket implies. Three of the five force it; two leave a choice, and the
    choice is what makes `dep_bundled` and `dep_distinct` readable at any price."""
    if bucket == "free_bundled":
        return "no_separate_charge"
    if bucket == "priced_silent":
        return "separate_fee"
    if bucket == "unpriced_silent":
        return "not_stated"
    return None                     # decided by the caller, which knows the line type


def _fee_text(rng, charge, line_type):
    if charge == "no_separate_charge":
        return "included at no separate charge"
    if charge == "not_stated":
        return "fee not separately stated"
    base = {"subscription_platform": (48, 260), "implementation_services": (12, 96),
            "training_days": (4, 24), "support_tier": (6, 40),
            "usage_component": (5, 45), "renewal_option": (10, 120),
            "optional_module": (8, 60)}[line_type]
    return "USD %s" % format(rng.randrange(base[0], base[1]) * 1000, ",")


def _label_for(rng, line_type):
    tpl = rng.choice(LABELS[line_type])
    if "%s" in tpl:
        return tpl % rng.choice(EDITIONS)
    if "%d" in tpl:
        return tpl % rng.choice((2, 3, 4, 5, 8, 10))
    return tpl


def _dependency_sentence(rng, line_type, dependency):
    if dependency == "required_first":
        return rng.choice(PREREQ_SENTENCES[line_type])
    if dependency == "separately_available":
        return rng.choice(SEPARABLE_SENTENCES)
    return None


def _timing_sentence(rng, timing):
    if timing == "period":
        return rng.choice(PERIOD_SENTENCES) % rng.choice(TERM_MONTHS)
    if timing == "event":
        return rng.choice(EVENT_SENTENCES)
    return None


def build_all(rng, n=N_RECORDS):
    # ---- 1. contract shapes, exact ------------------------------------------------------------
    sizes = _deal(rng, n, [(k, c) for k, c in CONTRACT_SIZES]) if n == N_RECORDS else \
        _deal(rng, n, [(k, max(1, round(c * n / N_RECORDS))) for k, c in CONTRACT_SIZES])
    types_per_contract = []
    for size in sizes:
        extra = rng.sample(OPTIONAL_TYPES, min(size - 1, len(OPTIONAL_TYPES)))
        types_per_contract.append([SUB] + sorted(extra))

    slots = [t for ts in types_per_contract for t in ts]
    total = len(slots)

    # ---- 2. the two independent compositions, dealt over eligible slots ------------------------
    sep_spec = SEPARATION_BUCKETS if total == N_LINES else \
        [(k, max(1, round(c * total / N_LINES))) for k, c in SEPARATION_BUCKETS]
    tim_spec = TIMING_BUCKETS if total == N_LINES else \
        [(k, max(1, round(c * total / N_LINES))) for k, c in TIMING_BUCKETS]
    sep_spec = _fit(sep_spec, total)
    tim_spec = _fit(tim_spec, total)

    sep_bucket = _allocate(rng, slots, sep_spec, {
        "dep_bundled": CAN_BE_PREREQUISITE,
        "free_bundled": CAN_BE_UNPRICED,
        "unpriced_silent": CAN_BE_UNPRICED,
    })
    tim_bucket = _allocate(rng, slots, tim_spec, {"event": CAN_BE_EVENT})

    # ⚑ THE SHARPEST CASE, FORCED RATHER THAN HOPED FOR: `dep_distinct` lines that the order form
    # prices at NOTHING. The money column and the answer point opposite ways, and a reader who
    # decides separability from the fee gets exactly these wrong.
    free_distinct = [i for i, b in enumerate(sep_bucket)
                     if b == "dep_distinct" and slots[i] in CAN_BE_UNPRICED]
    rng.shuffle(free_distinct)
    forced_free = set(free_distinct[:N_FREE_BUT_DISTINCT])
    if len(forced_free) < N_FREE_BUT_DISTINCT:
        raise RuntimeError("only %d free-but-distinct slots available, wanted %d"
                           % (len(forced_free), N_FREE_BUT_DISTINCT))

    # ---- 3. decoys, dealt across contracts -----------------------------------------------------
    withdrawn = _deal(rng, n, [(True, N_WITHDRAWN), (False, n - N_WITHDRAWN)])
    ratecard = _deal(rng, n, [(True, N_RATE_CARD), (False, n - N_RATE_CARD)])
    carryover = _deal(rng, n, [(True, N_CARRYOVER), (False, n - N_CARRYOVER)])

    # ---- 4. emit -------------------------------------------------------------------------------
    stats = {"separation": {}, "pattern": {}, "buckets": {b: 0 for b, _ in SEPARATION_BUCKETS},
             "free_but_distinct": 0, "withdrawn": 0, "rate_card": 0, "carryover": 0,
             "needs_review": 0, "lines": 0}
    out = []
    cursor = 0
    for idx in range(n):
        line_types = types_per_contract[idx]
        rec_id = "OBX-%04d" % (idx + 1)
        used_codes = set()

        def code():
            while True:
                c = "PO-%04d" % rng.randrange(1000, 9999)
                if c not in used_codes:
                    used_codes.add(c)
                    return c

        obligations, sections = [], []
        for line_type in line_types:
            bucket = sep_bucket[cursor]
            timing = tim_bucket[cursor]
            forced = cursor in forced_free
            cursor += 1

            dependency = {"dep_bundled": "required_first",
                          "dep_distinct": "separately_available"}.get(bucket, "silent")
            charge = _charge_for(rng, bucket)
            if charge is None:
                if forced:
                    charge = "no_separate_charge"
                elif line_type == SUB:
                    charge = "separate_fee"
                elif bucket == "dep_bundled":
                    charge = rng.choice(["separate_fee", "separate_fee", "not_stated"])
                else:
                    charge = rng.choice(["separate_fee", "separate_fee", "no_separate_charge",
                                         "not_stated"])

            d = RB.decide(charge, dependency, timing)
            item = {
                "item_code": code(),
                "item_label": _label_for(rng, line_type),
                "item_type": line_type,
                "charge": charge,
                "dependency": dependency,
                "timing": timing,
                "separation": d["separation"],
                "pattern": d["pattern"],
            }
            obligations.append(item)
            sections.append((item, _fee_text(rng, charge, line_type),
                             _dependency_sentence(rng, line_type, dependency),
                             _timing_sentence(rng, timing)))
            stats["buckets"][bucket] += 1
            if forced:
                stats["free_but_distinct"] += 1
            stats["separation"][d["separation"]] = stats["separation"].get(d["separation"], 0) + 1
            stats["pattern"][d["pattern"]] = stats["pattern"].get(d["pattern"], 0) + 1
            stats["lines"] += 1

        decoys = []
        wd = None
        if withdrawn[idx]:
            wtype = rng.choice(OPTIONAL_TYPES)
            wd = {"item_code": code(), "item_label": _label_for(rng, wtype), "item_type": wtype,
                  "amendment": "A-%d" % rng.randrange(1, 4)}
            decoys.append({"item_code": wd["item_code"], "kind": "withdrawn"})
            stats["withdrawn"] += 1
        rc = None
        if ratecard[idx]:
            rc = {"item_code": code(), "rate": format(rng.randrange(85, 220) * 10, ",")}
            decoys.append({"item_code": rc["item_code"], "kind": "rate_card"})
            stats["rate_card"] += 1
        co = None
        if carryover[idx]:
            ctype = rng.choice(OPTIONAL_TYPES)
            co = {"item_code": code(), "item_label": _label_for(rng, ctype),
                  "order_form": "OF-%05d" % rng.randrange(10000, 49999)}
            decoys.append({"item_code": co["item_code"], "kind": "carryover"})
            stats["carryover"] += 1

        customer = "%s %s" % (rng.choice(CUST_A), rng.choice(CUST_B))
        segment = rng.choice(SEGMENTS)
        account = "AC-%05d" % rng.randrange(10000, 99999)
        billing = "BC-%04d" % rng.randrange(1000, 9999)
        order_form = "OF-%05d" % rng.randrange(50000, 99999)
        signed = "2026-%02d-%02d" % (rng.randrange(1, 9), rng.randrange(1, 28))

        text = _render(rec_id, customer, segment, account, billing, order_form, signed,
                       sections, wd, rc, co)

        needs = _needs_review(obligations)
        if needs:
            stats["needs_review"] += 1

        gold = {"contract_id": rec_id, "order_form_ref": order_form,
                "obligations": obligations, "decoys": decoys,
                "needs_drafting_review": needs}
        out.append((rec_id, text, gold))

    assert cursor == total, "consumed %d of %d line slots" % (cursor, total)
    return out, stats


def _fit(spec, total):
    """Round a scaled composition back onto `total` exactly, adjusting the largest bucket."""
    got = sum(c for _n, c in spec)
    if got == total:
        return list(spec)
    spec = [list(x) for x in spec]
    big = max(range(len(spec)), key=lambda i: spec[i][1])
    spec[big][1] += total - got
    return [(n, c) for n, c in spec]


def _needs_review(obligations):
    """THE BUSINESS CONDITION, computed here exactly as src/extract.py::compute() computes it over
    a reply. Kept as a tiny local copy ONLY so the generator does not import the extractor (which
    imports the adapters, which is a lot of machinery for a build script); the real definition is
    in src/extract.py and evals/check_labels.py asserts the two agree on every gold row."""
    return any(o["charge"] == "separate_fee" and o["separation"] == "not_determined"
               and o["pattern"] == "not_determined" for o in obligations)


def _render(rec_id, customer, segment, account, billing, order_form, signed, sections, wd, rc, co):
    """One contract pack. Section headings are short by design -- the line's own description lives
    in the section BODY, so a long product name can never push a heading past what src/segment.py
    will read as one."""
    lines = [_underline("Contract"), rec_id, ""]
    lines += [_underline("Customer Reference"),
              "%s (%s), account %s, billing contact %s."
              % (customer, segment, account, billing), ""]

    rows = []
    for item, fee, _dep, _tim in sections:
        rows.append("  %-9s %-52s %s" % (item["item_code"], item["item_label"], fee))
    if wd is not None:
        rows.append("  %-9s %-52s %s" % (wd["item_code"], wd["item_label"],
                                         "WITHDRAWN by amendment %s -- not supplied under this "
                                         "order form" % wd["amendment"]))
    lines += [_underline("Order Form"),
              "Order form %s, signed %s. Currency USD. Lines as ordered:" % (order_form, signed),
              ""] + rows + [""]

    for item, fee, dep, tim in sections:
        body = ["Description: %s" % item["item_label"],
                "Type: %s" % item["item_type"],
                "Fee on the order form: %s" % fee]
        if dep:
            body.append(dep)
        if tim:
            body.append(tim)
        lines += [_underline("Item %s" % item["item_code"])] + body + [""]

    if wd is not None:
        lines += [_underline("Item %s" % wd["item_code"]),
                  "Description: %s" % wd["item_label"],
                  "Type: %s" % wd["item_type"],
                  "Fee on the order form: withdrawn",
                  "This clause was drafted before amendment %s and is retained in the pack for "
                  "the audit trail." % wd["amendment"], ""]

    if rc is not None:
        lines += [_underline("Professional Services Rate Card"),
                  "Rate card reference %s, consultancy day rate USD %s per day."
                  % (rc["item_code"], rc["rate"]),
                  "No services are ordered under this order form. These rates apply only to work "
                  "ordered later under a separate statement of work.", ""]

    if co is not None:
        lines += [_underline("Continuing Items From An Earlier Order Form"),
                  "Item %s, %s, was supplied under order form %s and continues in effect."
                  % (co["item_code"], co["item_label"], co["order_form"]),
                  "It is not re-ordered here and is listed for context only.", ""]

    notes = ["This pack is a draft for review."]
    if wd is not None:
        notes.append("Amendment %s removed line %s before signature; it is not supplied under "
                     "this order form." % (wd["amendment"], wd["item_code"]))
    # Indexed off the record number rather than drawn, so the closing note is a property of the
    # pack and not another draw the seeded RNG has to keep in step.
    notes.append(CLOSING_NOTES[int(rec_id[-4:]) % len(CLOSING_NOTES)])
    lines += [_underline("Contract Notes")] + notes + [""]

    return "\n".join(lines) + "\n"


FEE_TEXT_FOR = {"no_separate_charge": "included at no separate charge",
                "not_stated": "fee not separately stated"}


def _verify(rows):
    """Every gold value must be stated in the pack it labels, and every gold call must be that
    line's own rulebook lookup. A corpus whose labels are not readable off its own text is not a
    corpus, it is a second opinion."""
    for rec_id, text, gold in rows:
        assert gold["contract_id"] in text, "%s: contract_id not stated" % rec_id
        assert gold["order_form_ref"] in text, "%s: order_form_ref not stated" % rec_id
        for o in gold["obligations"]:
            assert o["item_code"] in text, "%s: %s not stated" % (rec_id, o["item_code"])
            assert o["item_label"] in text, "%s: label of %s not stated" % (rec_id, o["item_code"])
            assert "Type: %s" % o["item_type"] in text, \
                "%s: type of %s not stated" % (rec_id, o["item_code"])
            want = FEE_TEXT_FOR.get(o["charge"])
            if want is not None:
                assert want in text, "%s: charge of %s not stated verbatim" % (rec_id,
                                                                              o["item_code"])
            d = RB.decide(o["charge"], o["dependency"], o["timing"])
            assert d["separation"] == o["separation"], \
                "%s: %s gold separation %r disagrees with its own rulebook lookup (%r)" \
                % (rec_id, o["item_code"], o["separation"], d["separation"])
            assert d["pattern"] == o["pattern"], \
                "%s: %s gold pattern %r disagrees with its own rulebook lookup (%r)" \
                % (rec_id, o["item_code"], o["pattern"], d["pattern"])
        for dc in gold["decoys"]:
            assert dc["item_code"] in text, "%s: decoy %s not stated" % (rec_id, dc["item_code"])
            assert dc["item_code"] not in {o["item_code"] for o in gold["obligations"]}, \
                "%s: decoy %s collides with an ordered line" % (rec_id, dc["item_code"])
        # ⚑ EVERY `separately_available` LINE MUST CARRY ONE OF THE THREE SENTENCES THAT SAY SO,
        # and every `silent` line must carry none of them. This is the invariant the whole
        # `not_determined` class rests on: if a silent line's clause accidentally read as a
        # dependency statement, gold would be wrong and the model would be marked down for being
        # right.
        for o in gold["obligations"]:
            sec = _section_of(text, "Item %s" % o["item_code"])
            said_sep = any(s in sec for s in SEPARABLE_SENTENCES)
            said_pre = any(s in sec for group in PREREQ_SENTENCES.values() for s in group)
            if o["dependency"] == "separately_available":
                assert said_sep and not said_pre, "%s: %s claims separable and does not say so" \
                    % (rec_id, o["item_code"])
            elif o["dependency"] == "required_first":
                assert said_pre and not said_sep, "%s: %s claims prerequisite and does not say so" \
                    % (rec_id, o["item_code"])
            else:
                assert not said_sep and not said_pre, \
                    "%s: %s is silent in gold and its clause states a dependency" \
                    % (rec_id, o["item_code"])


def _section_of(text, heading):
    i = text.find(heading + "\n" + "-" * len(heading))
    if i < 0:
        return ""
    j = text.find("\n\n", i)
    return text[i:j if j > 0 else len(text)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_RECORDS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for rec_id, text, _gold in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    total_bytes = sum(len(t.encode("utf-8")) for _i, t, _g in rows)
    print("contracts: %d   lines: %d   bytes: %d" % (len(rows), stats["lines"], total_bytes))
    print("separation: %s"
          % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["separation"].items())))
    print("pattern:    %s"
          % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["pattern"].items())))
    print("buckets:    %s" % "  ".join("%s=%d" % (k, stats["buckets"][k])
                                       for k, _c in SEPARATION_BUCKETS))
    print("%d line(s) are priced at NOTHING and are still `distinct` -- the money column and the "
          "answer point opposite ways" % stats["free_but_distinct"])
    print("%d withdrawn line(s), %d rate card(s), %d carried-over item(s) -- %d decoy codes that "
          "must NOT reach the worksheet"
          % (stats["withdrawn"], stats["rate_card"], stats["carryover"],
             stats["withdrawn"] + stats["rate_card"] + stats["carryover"]))
    print("%d contract(s) carry a PRICED line whose separation AND delivery pattern the paperwork "
          "settles neither of -- the pure-code review flag" % stats["needs_review"])
    print("internal consistency check: PASSED (every gold value is stated in its own pack, every "
          "call is that line's own rulebook lookup, and every silent line's clause really is "
          "silent)")


if __name__ == "__main__":
    main()
