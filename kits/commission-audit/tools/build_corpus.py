#!/usr/bin/env python3
"""Generate synthetic channel-commission claim records and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one commission claim line, joined to the property's own folio record,
per file) and data/gold.jsonl, byte-identical on every run. Every claim id, confirmation number,
property name and reviewer note here is invented -- nothing is fetched and nothing is licensed
from anybody, so the corpus ships under this repo's MIT licence. No real booking channel, travel
agency, hotel brand or guest is named, and no real commission agreement is reproduced. See
data/SOURCES.md.

⚑ THE CHANNEL IS NEVER NAMED, ANYWHERE, AND THAT IS DELIBERATE. `booking_source` is an enum whose
"came through the booking channel this invoice is from" value is the literal token `channel`. A
brand name in a corpus about disputed money is a claim about a real company's invoicing, and this
repo does not make one.

⚑ GOLD `claim_valid` IS A COMPUTATION, NOT A LABEL SOMEBODY TYPED. It is derived from the same
structured folio values the generator itself decided, with the same rule the kit publishes
everywhere else:

    owed_commission(...) == claimed_commission_usd

It is never re-derived from the property reviewer's own note, and the note never feeds the label.

⚑ THE RULE, AND WHY IT HAS A PRIORITY ORDER. Five branches, and four of them are checks a reader
doing the arithmetic first will skip:

  1. SOURCE OUTRANKS EVERYTHING. A booking the folio shows arrived direct, through a corporate GDS
     or as a walk-in owes this channel nothing -- however real the stay, however tidy the
     arithmetic. Check the source before computing anything.
  2. NOTHING IS OWED TWICE. A stay already commissioned on a previous invoice owes nothing on this
     one, even though every other value on the line is correct.
  3. THE BASE IS ROOM REVENUE NET OF REFUNDS, AND NEVER THE TAXES AND FEES BESIDE IT. Non-room
     charges sit on the same folio and are not commissionable, so a claim computed on the folio
     total is always too high.
  4. A CANCELLATION OR NO-SHOW IS NOT AUTOMATICALLY ZERO. When a penalty was actually charged,
     commission IS owed -- on the penalty, not on the room revenue that was never earned. A reader
     who stops at "the guest did not stay" gets these backwards.
  5. A REBOOKED RESERVATION IS A STAY. The guest moved to a new confirmation number and stayed;
     the commission is owed on that stay's room revenue exactly as if nothing had moved.

⚑ THE PLANTED AMBIGUITY: validity is folio arithmetic, and the property reviewer's own note
disagrees with it on `N_AMBIGUOUS` of records. A genuinely bad claim carries an accepting note
("Folio matches the claim, no action needed."); a claim that is exactly right carries a note that
reads as a dispute ("Flagged by the night auditor -- amount looked high against the folio.").
Anything that classifies validity off the note's TONE -- including evals/baseline.py, deliberately
-- fails those records by construction. Anything that runs the computation gets them right.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 55

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the discipline every kit
# in this series has used since a sibling generator asked for 40 pct ambiguity and delivered 51
# pct. A count 1.7 standard deviations off its own design is not a corpus property, it is sampling
# noise being published as one. So each class here is a fixed COUNT, shuffled by the seeded RNG.
# The corpus is still deterministic and still byte-identical on every run.
N_VALID = 28                       # claimed_commission_usd equals what the rule computes
N_AMBIGUOUS = 22                   # 40 pct, exactly -- a reviewer note from the wrong register
N_PAID = 30                        # invoice_status == "paid"; the rest are still "unpaid"

# Invented properties. Nothing here is a real hotel, brand or management company -- names built so
# a reader can see at a glance that the corpus is a construction.
#
# ⚠︎ A NEAR-MISS IS A BRAND NAME. A first version of this list carried "Fairmount Lodge", which is
# one letter from a real global hotel brand, and "a reader will see it is invented" is not a test
# anybody applies to a name they half-recognise. Renamed before the corpus shipped. The property
# is the one section no field maps to and is therefore never sent to a model -- which is exactly
# why it is easy to be careless with it, and exactly no excuse.
PROPERTIES = [
    "Harbour Point Hotel - Northgate",
    "Cedar Mill Inn - Riverside",
    "Quillon Suites - Airport West",
    "Lantern Bay Hotel - Old Quarter",
    "Marloe Field Lodge - Lakeside",
    "Kestrel House - City Centre",
    "Amberly Court Hotel - Southbank",
    "Windrow Inn - Fairgrounds",
]

FOLIO_STATUSES = ["stayed", "cancelled", "no_show", "rebooked"]
# ⚠︎ `channel` IS THE NEUTRAL TOKEN FOR "THIS INVOICE'S OWN BOOKING CHANNEL". The other three are
# the ways a booking reaches a property WITHOUT the channel earning anything.
BOOKING_SOURCES = ["channel", "direct", "corporate_gds", "walk_in"]

# ⚑ THE VALID SHAPES. Exact counts, and four of the five are the hard cases the whole kit exists
# to test -- a plain correct stay is the easy one and is deliberately a minority of them.
VALID_SHAPES = [
    ("stayed_plain", 10),          # a channel stay, commission on room revenue, exact
    ("rebooked", 5),               # the guest moved confirmation numbers and stayed; still owed
    ("cancel_with_penalty", 5),    # cancelled inside the penalty window -- owed ON THE PENALTY
    ("no_show_with_penalty", 4),   # same, on a no-show
    ("refund_net", 4),             # a partly-refunded stay, claimed correctly on the NET revenue
]

# ⚑ THE FAULT LIBRARY. Every way a commission claim line can be wrong, and the exact number of the
# 27 invalid records each one takes.
FAULTS = [
    ("taxes_in_base", 6),          # commission computed on the folio TOTAL, taxes and fees included
    ("wrong_channel", 5),          # a claim on a booking the folio shows came direct/GDS/walk-in
    ("duplicate_claim", 4),        # already commissioned on a previous invoice, claimed again
    ("refund_ignored", 5),         # a partly-refunded stay claimed on GROSS room revenue
    ("cancel_no_penalty", 4),      # cancelled with no penalty charged, commission claimed anyway
    ("rate_mismatch", 3),          # a percentage other than the contracted one applied
]

# Notes whose TONE says "this claim line is fine". Used truthfully on a valid claim, and against
# type on an invalid one -- half the planted ambiguity.
ACCEPTING_NOTES = [
    "Standard channel booking, nothing unusual on this line.",
    "Folio matches the claim, no action needed.",
    "Routine line, previously approved by the front-office manager.",
    "Checked against the folio last cycle and it came out clean.",
]

# Notes whose TONE says "something is wrong with this claim". Used truthfully on an invalid claim,
# and against type on one that is exactly right -- the other half.
DISPUTING_NOTES = [
    "Flagged by the night auditor -- amount looked high against the folio.",
    "Disputed with the channel last month; awaiting their response.",
    "Not confident this line is owed -- second look before payment.",
    "Something looked off against the folio on this line, revisit before settlement.",
]

CONTRACT_RATES = [10.0, 12.0, 12.5, 15.0, 17.5, 18.0]


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs, padded with the
    first pair's value if the counts fall short. Deterministic under the seeded RNG."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    while len(out) < n:
        out.append(spec[0][0])
    out = out[:n]
    rng.shuffle(out)
    return out


def owed_commission(folio_status, booking_source, already_commissioned,
                    room_revenue_usd, room_revenue_refunded_usd, penalty_charged_usd,
                    contract_rate_pct):
    """THE RULE, in one place. src/reconcile.py::owed_commission() is the same function, run over
    the MODEL's own extracted values; data/fields.json states it to the model in words. Three
    readers, one definition, so the corpus, the prompt and the guardrail cannot drift apart about
    what a commission claim being valid means.

    Returns the commission owed, in dollars, rounded to the cent.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED COMMISSION STRUCTURE, NOT A REAL CHANNEL AGREEMENT. No
    booking channel's published terms, no signed distribution agreement and no real commission
    schedule was consulted, and none is reproduced. A real agreement carries a rate grid by room
    type and season, a cancellation-window table, a disputed-claim procedure and a settlement
    calendar; this is five branches and one multiplication, chosen because it is the smallest rule
    that is genuinely useful and readable off one folio.
    """
    # 1. The channel earns nothing on a booking that did not come through it.
    if booking_source != "channel":
        return 0.0
    # 2. Nothing is owed twice.
    if already_commissioned == "yes":
        return 0.0
    # 3. The commissionable base. Non-room charges are on the same folio and never enter it.
    if folio_status in ("stayed", "rebooked"):
        base = (room_revenue_usd or 0.0) - (room_revenue_refunded_usd or 0.0)
    else:                                   # cancelled or no_show
        base = penalty_charged_usd or 0.0
    if base <= 0:
        return 0.0
    return round(base * contract_rate_pct / 100.0, 2)


def _money(rng, lo, hi):
    return round(rng.uniform(lo, hi), 2)


def _valid_facts(rng, shape, rate):
    """(folio_status, booking_source, already, room_rev, refunded, penalty, claimed) for a record
    whose claimed commission is exactly what the rule computes."""
    if shape == "stayed_plain":
        rev = _money(rng, 240, 3400)
        non_room = round(rev * rng.uniform(0.12, 0.28), 2)
        st, src, already, refunded, penalty = "stayed", "channel", "no", 0.0, None
    elif shape == "rebooked":
        rev = _money(rng, 320, 2900)
        non_room = round(rev * rng.uniform(0.12, 0.28), 2)
        st, src, already, refunded, penalty = "rebooked", "channel", "no", 0.0, None
    elif shape == "cancel_with_penalty":
        rev = 0.0
        penalty = _money(rng, 90, 640)
        non_room = round(penalty * rng.uniform(0.05, 0.18), 2)
        st, src, already, refunded = "cancelled", "channel", "no", None
    elif shape == "no_show_with_penalty":
        rev = 0.0
        penalty = _money(rng, 110, 520)
        non_room = round(penalty * rng.uniform(0.05, 0.18), 2)
        st, src, already, refunded = "no_show", "channel", "no", None
    elif shape == "refund_net":
        rev = _money(rng, 600, 3200)
        refunded = round(rev * rng.uniform(0.15, 0.55), 2)
        non_room = round(rev * rng.uniform(0.12, 0.28), 2)
        st, src, already, penalty = "rebooked" if rng.random() < 0.3 else "stayed", "channel", \
            "no", None
    else:
        raise ValueError(shape)
    claimed = owed_commission(st, src, already, rev, refunded, penalty, rate)
    return st, src, already, rev, refunded, penalty, non_room, claimed


def _fault_facts(rng, fault, rate, alt_source="direct"):
    """The same tuple, for a record whose claimed commission is NOT what the rule computes. Each
    branch is a specific, nameable way a channel's own invoice line goes wrong.

    `alt_source` is dealt by the caller rather than drawn here, so that all three non-channel
    booking sources are actually exercised. Drawn per record, five wrong_channel faults left
    `walk_in` unused on this seed -- an allowed enum value no record in the corpus states is a
    value the run never measures, and finding that out from the published counts is too late.
    """
    if fault == "taxes_in_base":
        # Commission computed on the folio TOTAL. Non-room charges are forced well clear of zero
        # so the fault is genuinely visible in the arithmetic rather than lost in rounding.
        rev = _money(rng, 420, 3100)
        non_room = round(rev * rng.uniform(0.14, 0.30), 2)
        claimed = round((rev + non_room) * rate / 100.0, 2)
        return "stayed", "channel", "no", rev, 0.0, None, non_room, claimed

    if fault == "wrong_channel":
        # A real stay with tidy arithmetic -- on a booking that never came through this channel.
        rev = _money(rng, 300, 2600)
        non_room = round(rev * rng.uniform(0.12, 0.28), 2)
        claimed = round(rev * rate / 100.0, 2)
        return "stayed", alt_source, "no", rev, 0.0, None, non_room, claimed

    if fault == "duplicate_claim":
        # Every value on the line is right. It was already commissioned last cycle.
        rev = _money(rng, 300, 2800)
        non_room = round(rev * rng.uniform(0.12, 0.28), 2)
        claimed = round(rev * rate / 100.0, 2)
        return "stayed", "channel", "yes", rev, 0.0, None, non_room, claimed

    if fault == "refund_ignored":
        # A partly-refunded stay, claimed on the GROSS room revenue.
        rev = _money(rng, 700, 3300)
        refunded = round(rev * rng.uniform(0.18, 0.55), 2)
        non_room = round(rev * rng.uniform(0.12, 0.28), 2)
        claimed = round(rev * rate / 100.0, 2)
        return "stayed", "channel", "no", rev, refunded, None, non_room, claimed

    if fault == "cancel_no_penalty":
        # Cancelled outside the penalty window: nothing was charged, so nothing is commissionable.
        # The claim is on the room revenue the property never earned.
        would_have_been = _money(rng, 260, 2400)
        non_room = 0.0
        claimed = round(would_have_been * rate / 100.0, 2)
        st = "cancelled" if rng.random() < 0.5 else "no_show"
        return st, "channel", "no", 0.0, None, 0.0, non_room, claimed

    if fault == "rate_mismatch":
        # A percentage other than the contracted one. Chosen from the same list so the wrong rate
        # is a plausible rate rather than an obvious typo.
        rev = _money(rng, 380, 3000)
        non_room = round(rev * rng.uniform(0.12, 0.28), 2)
        other = rng.choice([r for r in CONTRACT_RATES if abs(r - rate) >= 2.0])
        claimed = round(rev * other / 100.0, 2)
        return "stayed", "channel", "no", rev, 0.0, None, non_room, claimed

    raise ValueError(fault)


def build_all(rng, n=N_RECORDS):
    stats = {"valid": 0, "invalid": 0, "ambiguous": 0, "needs_recovery": 0,
             "faults": {name: 0 for name, _ in FAULTS},
             "shapes": {name: 0 for name, _ in VALID_SHAPES}}

    n_valid = min(N_VALID, n)
    n_invalid = n - n_valid
    shapes = _deal(rng, n_valid, VALID_SHAPES)
    faults = _deal(rng, n_invalid, FAULTS)
    # Which records are valid, dealt exactly and then shuffled with everything else.
    is_valid_deal = _deal(rng, n, [(True, n_valid), (False, n_invalid)])
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    paid = _deal(rng, n, [("paid", N_PAID), ("unpaid", n - N_PAID)])

    # Every non-channel source, dealt round-robin so all three are exercised rather than sampled.
    alt_sources = [BOOKING_SOURCES[1:][i % 3] for i in range(n)]

    # Every non-channel source, dealt round-robin over the wrong_channel faults themselves so all
    # three are exercised rather than sampled.
    alt_sources = BOOKING_SOURCES[1:]

    out = []
    si = fi = wci = 0
    for i in range(1, n + 1):
        prop = rng.choice(PROPERTIES)
        claim_id = "CLM-2026-%02d-%04d" % (rng.randint(1, 12), rng.randint(1000, 9999))
        confirmation = "BK-%s%s-%06d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                         rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                         rng.randint(100000, 999999))
        rate = rng.choice(CONTRACT_RATES)

        if is_valid_deal[i - 1]:
            shape = shapes[si]
            si += 1
            stats["shapes"][shape] += 1
            fault = None
            (status, source, already, rev, refunded,
             penalty, non_room, claimed) = _valid_facts(rng, shape, rate)
        else:
            fault = faults[fi]
            shape = None
            stats["faults"][fault] += 1
            (status, source, already, rev, refunded,
             penalty, non_room, claimed) = _fault_facts(
                rng, fault, rate, alt_sources[wci % len(alt_sources)])
            fi += 1
            if fault == "wrong_channel":
                wci += 1

        owed = owed_commission(status, source, already, rev, refunded, penalty, rate)
        valid = abs(claimed - owed) < 0.005
        stats["valid" if valid else "invalid"] += 1

        invoice_status = paid[i - 1]
        if (not valid) and invoice_status == "paid":
            stats["needs_recovery"] += 1

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the folio arithmetic normally, and contradicts it when ambiguous.
        accepting = valid if not ambiguous else (not valid)
        note = rng.choice(ACCEPTING_NOTES if accepting else DISPUTING_NOTES)

        refund_line = ("%.2f USD" % refunded if refunded is not None
                       else "not applicable (no room revenue was earned)")
        penalty_line = ("%.2f USD" % penalty if penalty is not None
                        else "not applicable (the stay was not cancelled)")

        rec_id = "CMA-%04d" % i
        lines = [
            _underline("Claim Line"), claim_id, "",
            _underline("Property"), prop, "",
            _underline("Confirmation Number"), confirmation, "",
            _underline("Folio Status"), status, "",
            _underline("Booking Source"), source, "",
            _underline("Room Revenue"), "%.2f USD" % rev, "",
            _underline("Room Revenue Refunded"), refund_line, "",
            _underline("Non-Room Charges"), "%.2f USD" % non_room, "",
            _underline("Cancellation Penalty"), penalty_line, "",
            _underline("Contract Rate"), "%.1f pct" % rate, "",
            _underline("Claimed Commission"), "%.2f USD" % claimed, "",
            _underline("Previously Commissioned"), already, "",
            _underline("Invoice Status"), invoice_status, "",
            _underline("Reviewer Note"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "claim_ref": rec_id,
            "claim_id": claim_id,
            "confirmation_number": confirmation,
            "folio_status": status,
            "booking_source": source,
            "room_revenue_usd": rev,
            "room_revenue_refunded_usd": refunded,
            "non_room_charges_usd": non_room,
            "penalty_charged_usd": penalty,
            "contract_rate_pct": rate,
            "claimed_commission_usd": claimed,
            "already_commissioned": already,
            "invoice_status": invoice_status,
            "reviewer_note": note,
            "claim_valid": "yes" if valid else "no",
            # NOT A FIELD THE MODEL IS ASKED FOR. Recorded in gold so a reader can see what the
            # rule computed beside what was claimed, and so _verify() can check the two.
            "_owed_commission_usd": owed,
            "_fault": fault,
            "_shape": shape,
        }
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, every gold label must be the
    computation the document's own values produce, and both nullable fields must be null exactly
    where the folio status says they are inapplicable. A corpus whose labels are not readable off
    its own text is not a corpus, it is a second opinion."""
    for rec_id, text, gold in rows:
        for field in ("claim_id", "confirmation_number", "folio_status", "booking_source",
                      "already_commissioned", "invoice_status", "reviewer_note"):
            assert gold[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        for field in ("room_revenue_usd", "non_room_charges_usd", "claimed_commission_usd"):
            assert "%.2f USD" % gold[field] in text, \
                "%s: %s not stated verbatim" % (rec_id, field)
        assert "%.1f pct" % gold["contract_rate_pct"] in text, \
            "%s: contract_rate_pct not stated verbatim" % rec_id

        # ⚑ THE TWO NULLABILITY INVARIANTS. They are complementary: a stay has a refund line and
        # no penalty line; a cancellation has a penalty line and no refund line.
        if gold["room_revenue_refunded_usd"] is None:
            assert gold["folio_status"] in ("cancelled", "no_show"), \
                "%s: refund is null on a stay" % rec_id
            assert "no room revenue was earned" in text, \
                "%s: null refund not explained in the document" % rec_id
        else:
            assert gold["folio_status"] in ("stayed", "rebooked"), \
                "%s: refund is stated on a cancellation" % rec_id
            assert "%.2f USD" % gold["room_revenue_refunded_usd"] in text, \
                "%s: refund not stated verbatim" % rec_id

        if gold["penalty_charged_usd"] is None:
            assert gold["folio_status"] in ("stayed", "rebooked"), \
                "%s: penalty is null on a cancellation" % rec_id
            assert "the stay was not cancelled" in text, \
                "%s: null penalty not explained in the document" % rec_id
        else:
            assert gold["folio_status"] in ("cancelled", "no_show"), \
                "%s: penalty is stated on a stay" % rec_id
            assert "%.2f USD" % gold["penalty_charged_usd"] in text, \
                "%s: penalty not stated verbatim" % rec_id

        want = owed_commission(gold["folio_status"], gold["booking_source"],
                               gold["already_commissioned"], gold["room_revenue_usd"],
                               gold["room_revenue_refunded_usd"], gold["penalty_charged_usd"],
                               gold["contract_rate_pct"])
        valid = abs(gold["claimed_commission_usd"] - want) < 0.005
        assert gold["claim_valid"] == ("yes" if valid else "no"), \
            "%s: gold label disagrees with its own values (rule says %.2f, claimed %.2f)" \
            % (rec_id, want, gold["claimed_commission_usd"])

        # ⚑ THE FAULT MUST ACTUALLY BE THE FAULT IT IS NAMED AS.
        if gold["_fault"] == "taxes_in_base":
            assert gold["non_room_charges_usd"] > 0, \
                "%s: a taxes_in_base fault with no non-room charges is not that fault" % rec_id
        if gold["_fault"] == "refund_ignored":
            assert gold["room_revenue_refunded_usd"] > 0, \
                "%s: a refund_ignored fault with no refund is not that fault" % rec_id
        if gold["_fault"] == "cancel_no_penalty":
            assert gold["penalty_charged_usd"] == 0.0, \
                "%s: a cancel_no_penalty fault with a penalty charged is not that fault" % rec_id
        if gold["_shape"] in ("cancel_with_penalty", "no_show_with_penalty"):
            assert gold["penalty_charged_usd"] > 0 and gold["claimed_commission_usd"] > 0, \
                "%s: a penalty-window shape must owe something" % rec_id

    # ⚑ EVERY ALLOWED ENUM VALUE MUST ACTUALLY OCCUR. An allowed value no record states is a value
    # the run never measures, and a published enum with an unexercised member is a claim about
    # coverage the corpus does not support.
    for field, allowed in (("folio_status", FOLIO_STATUSES),
                           ("booking_source", BOOKING_SOURCES)):
        seen = {g[field] for _i, _t, g in rows}
        missing = set(allowed) - seen
        assert not missing, "%s never occurs in the corpus: %s" % (field, sorted(missing))


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

    total = sum(len(t.encode("utf-8")) for _i, t, _g in rows)
    print("records: %d   valid: %d   invalid: %d   bytes: %d"
          % (len(rows), stats["valid"], stats["invalid"], total))
    print("faults: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["faults"].items()))
    print("valid shapes: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["shapes"].items()))
    print("%d (%.0f%%) carry a reviewer note whose TONE contradicts the folio arithmetic"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d record(s) are an invalid claim on an ALREADY-PAID invoice -- the pure-code "
          "recovery flag" % stats["needs_recovery"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every label is that document's own computation, both nullable fields are null exactly "
          "where the folio status makes them inapplicable)")


if __name__ == "__main__":
    main()
