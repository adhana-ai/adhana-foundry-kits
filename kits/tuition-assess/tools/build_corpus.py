#!/usr/bin/env python3
"""Generate synthetic student-account tuition assessment records and their gold labels, from a
fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one student account assessment per file) and data/gold.jsonl,
byte-identical on every run. Every account id, campus name, term code and bursar note here is
invented -- nothing is fetched and nothing is licensed from anybody, so the corpus ships under
this repository's MIT licence.

⚠︎ NO REAL STUDENT DATA, AND NOT ONE FIELD DERIVED FROM ANY. Tuition assessment is an
education-records domain; a real record names a real student, their enrolment, their aid and their
residency history. Nothing here is drawn from, sampled from or paraphrased out of a real account.
No real institution, real published tuition schedule, real fee table or real waiver programme is
named or reproduced. See data/SOURCES.md.

⚑ GOLD `assessment_correct` IS ARITHMETIC, NOT A LABEL SOMEBODY TYPED. It is derived from the same
four structured values the generator itself decided, run through the same rate table the kit
publishes everywhere else:

    correct_total(residency_tier, enrolled_credits, course_level, waiver_type) == assessed_total_usd

It is never re-derived from the bursar's note, and the note never feeds the label.

⚑ THE RATE TABLE, AND WHY IT HAS AN ORDER. A student at or above FULL_TIME_CREDITS is assessed the
flat full-time tuition band; below it, per enrolled credit. The threshold is INCLUSIVE, and the
flat band is deliberately CHEAPER than twelve credits at the per-credit rate, so the boundary is
worth money rather than being a rounding difference. On top of tuition sit two charges that behave
differently: a mandatory per-term fee that follows the same full-time/part-time split, and a
course-level differential fee charged per enrolled credit that is ZERO for Lower Division. A waiver
is applied LAST, and what it covers is a property of the waiver type -- three of the four cover
base tuition only, and NONE of the four ever covers the course-level differential fee.

⚑ THE TWO PLANTED DECOYS, BOTH OF THEM FIELDS THE MODEL MUST COPY AND NEITHER OF THEM EVIDENCE:

  1. THE RESIDENCY ACTION. `N_RECLASS` records carry a residency reclassification that took effect
     AFTER the term's census date. It does not change this term's assessment -- it applies from the
     following term. A model that recomputes tuition at the new tier gets a large, confident,
     wrong number. Six records are assessed that way on purpose, and fourteen carry the same
     reclassification correctly ignored, so the decoy cannot be read as "a reclassification means
     the total is wrong".
  2. THE BURSAR'S NOTE. `N_AMBIGUOUS` records carry a note from the wrong register -- a genuinely
     mis-assessed account with a breezy note, or a correctly assessed account whose note reads like
     a flagged problem. Anything that classifies correctness off the note's TONE -- including
     evals/baseline.py, deliberately -- fails those records by construction.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822

# ---------------------------------------------------------------------------------------------
# ⚠︎ THE RATE TABLE IS THIS KIT'S OWN INVENTION. No published tuition schedule, fee table, waiver
# programme or residency regulation was consulted, and none is reproduced. A real bursar's office
# reads a board-approved schedule with dozens of programme-specific rates, a separate fee bill by
# college, and aid packaging rules that sequence several awards; this is four values and an order,
# chosen because it is the smallest table that is genuinely hard and still readable off one reply.
# ---------------------------------------------------------------------------------------------

FULL_TIME_CREDITS = 12                                   # INCLUSIVE: exactly 12 is full-time

PER_CREDIT = {"In-State": 410, "Out-of-State": 1180}     # part-time band, per enrolled credit
FLAT_TERM = {"In-State": 4600, "Out-of-State": 13200}    # full-time band, flat for the term

# ⚑ THE FLAT BAND IS CHEAPER THAN 12 x THE PER-CREDIT RATE, ON PURPOSE. 12 x 410 = 4,920 against a
# flat 4,600 in-state; 12 x 1,180 = 14,160 against a flat 13,200 out-of-state. If the two agreed at
# the boundary the threshold would be untestable -- a model could read the band wrong and still
# produce the right number, and the corpus would be measuring nothing at exactly the point it is
# built to measure.

DIFFERENTIAL = {"Lower Division": 0, "Upper Division": 38, "Graduate": 65}   # per enrolled credit

MANDATORY_FULL = 612                                     # per term, full-time
MANDATORY_PART = 306                                     # per term, part-time

# (percentage waived, does it reach the mandatory fee). NOTHING here reaches the differential fee.
WAIVERS = {
    "None": (0, False),
    "Employee Tuition Remission": (100, False),
    "Staff Dependent Waiver": (50, False),
    "Regents Fee Waiver": (100, True),
}

# ⚑ EVERY WAIVER LANDS ON AN EVEN NUMBER, SO NO ROUNDING RULE IS NEEDED ANYWHERE. The only
# fractional percentage in the table is 50, and every amount it can be applied to is even: the
# per-credit rates (410, 1180) and the flat bands (4600, 13200) all are, and the 50 pct waiver
# never reaches a fee. A rate table that needs a rounding convention needs the model to be told
# which one, and "which way does it round" is a second question hiding inside the first.

N_RECORDS = 55
N_AMBIGUOUS = 22        # 40 pct exactly -- a bursar note from the contradicting register
N_POSTED = 30           # bill_status == "posted"; the rest are still "draft"
N_RECLASS = 20          # a mid-term residency reclassification on file (6 of them mis-applied)

# ⚑ THE FAULT LIBRARY. Every way an assessed total can depart from the rate table, and the exact
# number of the 27 mis-assessed records each one takes. Each fault changes EXACTLY ONE decision --
# that is asserted per record in _verify(), not assumed -- so `variance_reason` has one true
# answer rather than a defensible several.
FAULTS = [
    ("credit band", 8),        # the tuition band applied does not match the enrolled credit load
    ("residency tier", 6),     # tuition computed at the reclassified tier, which is next term's
    ("differential fee", 6),   # differential charged at the wrong course level's rate
    ("waiver coverage", 4),    # the waiver reached the mandatory fee, or failed to when it should
    ("mandatory fee", 3),      # the mandatory fee row read at the wrong band
]
N_CORRECT = N_RECORDS - sum(n for _f, n in FAULTS)        # 28

REASONS = ["none"] + [name for name, _n in FAULTS]

# Invented campuses. Nothing here is a real institution or a real campus.
CAMPUSES = [
    "Northgate Campus", "Riverbend Campus", "Stonehill Campus", "Lakemont Campus",
    "Fairhaven Campus", "Ashcombe Campus", "Highmoor Campus", "Cliffside Campus",
]

TIERS = ["In-State", "Out-of-State"]
LEVELS = ["Lower Division", "Upper Division", "Graduate"]

# term code -> the term's census date, the day enrolment and residency are frozen for assessment.
TERMS = {
    "2026-SP": "2026-01-26",
    "2026-SU": "2026-06-08",
    "2026-FA": "2026-09-14",
    "2027-SP": "2027-01-25",
}
# A reclassification effective AFTER the census date above. Same term, later in it.
MIDTERM_DATES = {
    "2026-SP": "2026-03-11",
    "2026-SU": "2026-07-02",
    "2026-FA": "2026-10-27",
    "2027-SP": "2027-03-09",
}

NO_ACTION = "None on file for this term."

# Notes whose TONE says "this account's assessment is fine". Used truthfully on a correctly
# assessed account, and against type on a mis-assessed one -- half the planted ambiguity.
BREEZY_NOTES = [
    "Standard assessment, nothing unusual to flag this term.",
    "Rate table confirmed current at the last schedule check.",
    "Routine account. No concerns from the bursar's office on this one.",
    "Charges look normal for this enrollment pattern, all in order.",
]

# Notes whose TONE says "something is wrong with this assessment". Used truthfully on a
# mis-assessed account, and against type on one assessed exactly right -- the other half.
ANXIOUS_NOTES = [
    "Escalated last term for a possible mis-assessment -- pending bursar review.",
    "Student disputed their residency classification; account under manual audit.",
    "Not confident this account is assessed correctly -- needs a second look before it posts.",
    "Something looked off on this account during the last fee review, revisit before closing.",
]


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


def assess(tier, credits, level, waiver, *,
           tuition_full=None, fee_full=None, diff_level=None, covers_mandatory=None):
    """THE RATE TABLE, in one place, with every decision overridable by exactly one keyword.

    src/extract.py::assess() is the same function, run over the MODEL's own extracted values;
    data/fields.json and src/prompt.py state it to the model in words. Three readers, one
    definition, so the corpus, the prompt and the guardrail cannot drift apart about what a
    correct assessment is.

    Called with no keywords it is the RULE. Each keyword substitutes one decision for the wrong
    one, which is how this generator builds a mis-assessed total that departs in exactly one place
    -- see FAULTS.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED RATE TABLE, NOT ANY INSTITUTION'S PUBLISHED SCHEDULE.
    """
    full_time = credits >= FULL_TIME_CREDITS
    tf = full_time if tuition_full is None else tuition_full
    ff = full_time if fee_full is None else fee_full
    dl = level if diff_level is None else diff_level
    pct, covers = WAIVERS[waiver]
    covers = covers if covers_mandatory is None else covers_mandatory

    tuition = FLAT_TERM[tier] if tf else credits * PER_CREDIT[tier]
    differential = credits * DIFFERENTIAL[dl]              # never waived, whatever the waiver is
    mandatory = MANDATORY_FULL if ff else MANDATORY_PART
    waivable = tuition + (mandatory if covers else 0)
    waived = waivable * pct // 100
    return tuition + differential + mandatory - waived


def departures(tier, credits, level, waiver, other_tier):
    """The five single-rule departures available on one record, as {reason: total}.

    Used twice, and the second use is what makes `variance_reason` an honest field: the generator
    picks one of these to build a mis-assessed record, and then _verify() checks that NO OTHER
    departure reproduces the same total. A number two different single mistakes could both explain
    has no single right reason, so it does not ship.
    """
    full_time = credits >= FULL_TIME_CREDITS
    wrong_level = {"Lower Division": "Upper Division",
                   "Upper Division": "Lower Division",
                   "Graduate": "Lower Division"}[level]
    _pct, covers = WAIVERS[waiver]
    return {
        "credit band": assess(tier, credits, level, waiver, tuition_full=not full_time),
        "residency tier": assess(other_tier, credits, level, waiver),
        "differential fee": assess(tier, credits, level, waiver, diff_level=wrong_level),
        "waiver coverage": assess(tier, credits, level, waiver, covers_mandatory=not covers),
        "mandatory fee": assess(tier, credits, level, waiver, fee_full=not full_time),
    }


# Which waiver types leave each fault OBSERVABLE. A 100 pct tuition waiver cancels any change to
# tuition, so a credit-band or residency departure under one produces the identical total and the
# record would be labelled mis-assessed while being arithmetically indistinguishable from correct.
# Every one of these was found by the assertion in _verify() before it was written down here.
FAULT_WAIVERS = {
    "credit band": ["None", "Staff Dependent Waiver"],
    "residency tier": ["None", "Staff Dependent Waiver"],
    "differential fee": list(WAIVERS),
    "waiver coverage": ["Employee Tuition Remission", "Staff Dependent Waiver",
                        "Regents Fee Waiver"],
    "mandatory fee": ["None", "Employee Tuition Remission", "Staff Dependent Waiver"],
}

# Credit loads, by group. The boundary counts are DESIGNED rather than drawn: 13 records sit at
# exactly 12 credits and 7 at exactly 11, and no other record is allowed either value, so the two
# numbers on the page are the two numbers the design asked for.
AT_12, JUST_UNDER = 12, 11
SPREAD_PART = [3, 4, 5, 6, 7, 8, 9, 10]
SPREAD_FULL = [13, 14, 15, 16, 17, 18]


def _credits(rng, group, k):
    """The credit load for record `k` of `group`."""
    if group == "correct":
        if k < 8:
            return AT_12
        if k < 12:
            return JUST_UNDER
        return rng.choice(SPREAD_PART + SPREAD_FULL)
    if group == "credit band":
        return AT_12 if k < 5 else JUST_UNDER
    return rng.choice(SPREAD_PART + SPREAD_FULL)


def _level(rng, group, k):
    """Course level. The differential-fee group is split by DESIGN across the two directions the
    fee can be got wrong -- charged on a Lower Division account that owes none, and omitted on an
    Upper Division or Graduate account that owes one -- because one direction alone would let a
    model that always answers "no differential" look competent."""
    if group == "differential fee":
        return ["Lower Division", "Lower Division", "Lower Division",
                "Upper Division", "Upper Division", "Graduate"][k]
    return rng.choice(LEVELS)


def build_all(rng, n=N_RECORDS):
    groups = _deal(rng, n, [("correct", N_CORRECT)] + FAULTS)

    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    posted = _deal(rng, n, [("posted", N_POSTED), ("draft", n - N_POSTED)])

    # A reclassification is FORCED on every residency-tier fault (the fault is not expressible
    # without one) and dealt to exactly enough of the rest to reach N_RECLASS.
    n_res_fault = dict(FAULTS)["residency tier"]
    extra_reclass = _deal(rng, n - n_res_fault,
                          [(True, N_RECLASS - n_res_fault),
                           (False, n - n_res_fault - (N_RECLASS - n_res_fault))])

    seen = {name: 0 for name in ["correct"] + [f for f, _c in FAULTS]}
    extra_i = 0
    out = []
    stats = {"correct": 0, "mismatch": 0, "ambiguous": 0, "needs_review": 0,
             "reclass": 0, "reclass_ignored": 0, "at_12": 0, "at_11": 0,
             "faults": {name: 0 for name, _c in FAULTS},
             "levels": {lv: 0 for lv in LEVELS}, "waivers": {w: 0 for w in WAIVERS},
             "retries": 0}

    for i in range(1, n + 1):
        group = groups[i - 1]
        k = seen[group]
        seen[group] += 1

        if group == "residency tier":
            reclass = True
        else:
            reclass = extra_reclass[extra_i]
            extra_i += 1

        # ⚑ A BOUNDED, SEEDED RE-DRAW, NOT A FIX-UP. A record whose mis-assessed total is
        # reproducible by two different single departures has no single true `variance_reason`,
        # so it is re-drawn rather than shipped with an arbitrary label. The loop is deterministic
        # under the seed; the retry count is printed so the reader can see it is small.
        for attempt in range(64):
            campus = rng.choice(CAMPUSES)
            account_id = "SA-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                           rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                           rng.randint(10000, 99999))
            term = rng.choice(sorted(TERMS))
            tier = rng.choice(TIERS)
            other_tier = "Out-of-State" if tier == "In-State" else "In-State"
            credits = _credits(rng, group, k)
            level = _level(rng, group, k)
            waiver = rng.choice(FAULT_WAIVERS[group] if group != "correct" else list(WAIVERS))

            correct_total = assess(tier, credits, level, waiver)
            alt = departures(tier, credits, level, waiver, other_tier)
            if group == "correct":
                assessed = correct_total
                reason = "none"
                ok = True
            else:
                assessed = alt[group]
                reason = group
                # Exactly one departure must explain this total, and it must be the labelled one.
                ok = (assessed != correct_total
                      and sum(1 for r, v in alt.items() if v == assessed) == 1)
            if ok:
                break
            stats["retries"] += 1
        else:
            raise AssertionError("record %d: could not draw an unambiguous %s fault" % (i, group))

        is_correct = assessed == correct_total
        stats["correct" if is_correct else "mismatch"] += 1
        if not is_correct:
            stats["faults"][reason] += 1
        stats["levels"][level] += 1
        stats["waivers"][waiver] += 1
        if credits == AT_12:
            stats["at_12"] += 1
        if credits == JUST_UNDER:
            stats["at_11"] += 1

        status = posted[i - 1]
        if (not is_correct) and status == "posted":
            stats["needs_review"] += 1

        if reclass:
            stats["reclass"] += 1
            if reason != "residency tier":
                stats["reclass_ignored"] += 1
            action = ("Reclassified to %s effective %s, after the term census date of %s."
                      % (other_tier, MIDTERM_DATES[term], TERMS[term]))
        else:
            action = NO_ACTION

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        breezy = is_correct if not ambiguous else (not is_correct)
        note = rng.choice(BREEZY_NOTES if breezy else ANXIOUS_NOTES)

        rec_id = "STU-%04d" % i
        lines = [
            _underline("Student Account"), account_id, "",
            _underline("Campus"), campus, "",
            _underline("Term"), term, "",
            _underline("Residency Tier"), tier, "",
            _underline("Enrolled Credits"), "%d credit hours" % credits, "",
            _underline("Course Level"), level, "",
            _underline("Waiver"), waiver, "",
            _underline("Assessed Total"), "%d USD" % assessed, "",
            _underline("Bill Status"), status, "",
            _underline("Residency Action"), action, "",
            _underline("Bursar Notes"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": rec_id,
            "student_account_id": account_id,
            "term_code": term,
            "residency_tier": tier,
            "enrolled_credits": credits,
            "course_level": level,
            "waiver_type": waiver,
            "assessed_total_usd": assessed,
            "bill_status": status,
            "residency_action": action,
            "bursar_notes": note,
            "assessment_correct": "yes" if is_correct else "no",
            "variance_reason": reason,
        }
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, every gold label must be that
    document's own arithmetic, and every mis-assessed total must have exactly ONE single-rule
    explanation. A corpus whose labels are not readable off its own text is not a corpus, it is a
    second opinion."""
    for rec_id, text, gold in rows:
        for field in ("student_account_id", "term_code", "residency_tier", "course_level",
                      "waiver_type", "bill_status", "residency_action", "bursar_notes"):
            assert gold[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        assert "%d credit hours" % gold["enrolled_credits"] in text, \
            "%s: enrolled_credits not stated verbatim" % rec_id
        assert "%d USD" % gold["assessed_total_usd"] in text, \
            "%s: assessed_total_usd not stated verbatim" % rec_id

        tier = gold["residency_tier"]
        other = "Out-of-State" if tier == "In-State" else "In-State"
        want = assess(tier, gold["enrolled_credits"], gold["course_level"], gold["waiver_type"])
        is_correct = want == gold["assessed_total_usd"]
        assert gold["assessment_correct"] == ("yes" if is_correct else "no"), \
            "%s: gold label disagrees with its own arithmetic (table says %d, assessed %d)" \
            % (rec_id, want, gold["assessed_total_usd"])

        assert (gold["variance_reason"] == "none") == is_correct, \
            "%s: variance_reason %r does not agree with assessment_correct %r" \
            % (rec_id, gold["variance_reason"], gold["assessment_correct"])

        if not is_correct:
            alt = departures(tier, gold["enrolled_credits"], gold["course_level"],
                             gold["waiver_type"], other)
            hits = [r for r, v in alt.items() if v == gold["assessed_total_usd"]]
            assert hits == [gold["variance_reason"]], \
                "%s: assessed total %d is explained by %s, not by %r alone" \
                % (rec_id, gold["assessed_total_usd"], hits, gold["variance_reason"])
        if gold["residency_action"] != NO_ACTION:
            assert other in gold["residency_action"], \
                "%s: the reclassification does not name the other tier" % rec_id
            assert gold["term_code"] in text, "%s: term missing" % rec_id


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
    print("records: %d   correct: %d   mis-assessed: %d   bytes: %d"
          % (len(rows), stats["correct"], stats["mismatch"], total))
    print("faults: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["faults"].items()))
    print("levels: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["levels"].items()))
    print("waivers: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["waivers"].items()))
    print("%d at exactly %d credits (the full-time threshold), %d at %d"
          % (stats["at_12"], AT_12, stats["at_11"], JUST_UNDER))
    print("%d carry a mid-term residency reclassification -- %d of them correctly ignored"
          % (stats["reclass"], stats["reclass_ignored"]))
    print("%d (%.0f%%) carry a bursar note whose TONE contradicts the arithmetic"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d record(s) are mis-assessed AND already posted -- the pure-code review flag"
          % stats["needs_review"])
    print("%d re-draw(s) were needed to keep every variance reason single-valued" % stats["retries"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every label is that document's own arithmetic, every variance has exactly one "
          "single-rule explanation)")


if __name__ == "__main__":
    main()
