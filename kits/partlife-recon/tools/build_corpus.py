#!/usr/bin/env python3
"""Generate synthetic life-limited-part record packs and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one component record pack per file) and data/gold.jsonl, byte-identical
on every run. Every component identifier, part reference, airframe reference, holding location and
reviewer note here is invented -- nothing is fetched and nothing is licensed from anybody, so the
corpus ships under this repo's MIT licence.

⚠︎ NO REAL AIRCRAFT MANUFACTURER, ENGINE TYPE, PART NUMBER, OPERATOR OR AIRWORTHINESS DIRECTIVE IS
NAMED OR REPRODUCED, and no manufacturer manual text is quoted. "Life limit", "cycles since new",
"time since overhaul", "life-limited part" and "return to service" are ordinary continuing-
airworthiness-records vocabulary; the STRUCTURE of a record pack is modelled and nothing else.

⚑ GOLD `life_status` IS AN ARITHMETIC RESULT, NOT A LABEL SOMEBODY TYPED. It is derived from the
same four figures the generator itself decided -- the reconstructed trail totals and the two
published limits -- plus whether a gap was declared, with the same rule the kit publishes
everywhere else:

    life_status(trail_hours, trail_cycles, limit_hours, limit_cycles, record_gap)

It is never re-derived from the component's own tag, and never from the reviewer's note.

⚑ THE RULE, AND WHY IT HAS THIS PRIORITY ORDER.

    a. at or past BOTH limits          -> "both_exceeded"
    b. at or past the hours limit      -> "hours_exceeded"
    c. at or past the cycles limit     -> "cycles_exceeded"
    d. a records gap is declared       -> "cannot_determine"
    e. otherwise                        -> "within_limits"

The exceedance checks come BEFORE the gap check, and that ordering is the sharpest test in this
corpus. A missing period of records can only ADD accumulated life; it can never bring a component
that the surviving records already put at or past a limit back inside it. So a gap makes
"within limits" undeterminable and leaves "exceeded" perfectly determinable. A reader (or a model)
that sees "records not available" and stops there answers `cannot_determine` on a component the
trail has already condemned.

⚠︎ AND THE LIMIT IS INCLUSIVE. At exactly the published limit there is no life remaining, so
trail == limit is EXCEEDED, not within limits.

⚑ THE OTHER THREE TRAPS, ALL OF THEM ARITHMETIC:

  1. HOURS AND CYCLES ARE SUMMED SEPARATELY. Each installation period ran on a different airframe
     at a different hours-to-cycles ratio, so deriving one total from the other with any single
     ratio is wrong by construction.
  2. AN OVERHAUL RESETS ONE COUNTER AND NOT THE OTHER. The trail line says so in words: time since
     overhaul goes to zero, time since new is unaffected. Restarting the accumulation at the
     overhaul undercounts the component's life, usually enormously.
  3. A DECLARED GAP CONTRIBUTES NOTHING. The period is stated, its accrual is not, and the honest
     total is the sum of what the records substantiate -- never an interpolation.

⚑ THE PLANTED AMBIGUITY: the reviewer's own note is written in the register that CONTRADICTS the
record on `N_NOTE_MISMATCH` of the packs -- a calm "nothing outstanding" over a component that is
past its cycles limit, a worried "please double-check this one" over a component that is comfortably
inside both. No note ever states a figure or a status word (asserted in _verify), so it is never
evidence about anything and every reader that leans on it is taking a shortcut.

⚠︎ WHAT THIS CORPUS IS NOT. It is not an airworthiness determination and neither is the kit. Gold
records what the trail substantiates and where it disagrees with the tag; nothing here releases a
component to service.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 50

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the same discipline the
# sibling kits in this series settled on after one generator asked for 40 pct ambiguity and
# delivered 51 pct. A count 1.7 standard deviations off its own design is not a corpus property,
# it is sampling noise being published as one. Each class here is a fixed COUNT, shuffled by the
# seeded RNG, so the numbers on the page are the numbers the design asked for.
FAULTS = [
    ("clean", 24),        # inside both limits, no gap declared
    ("hours_over", 5),    # at or past the hours limit, inside the cycles limit
    ("cycles_over", 6),   # inside the hours limit, at or past the cycles limit
    ("both_over", 3),     # at or past both
    ("gap_open", 7),      # a declared gap, and what survives is inside both limits
    ("gap_over", 5),      # a declared gap, AND what survives is ALREADY past a limit
]
N_TAG_MISMATCH = 14       # the tag's own figures disagree with the reconstructed trail total
N_OVERHAUL = 16           # an overhaul line sits mid-trail, resetting one counter and not the other
N_RTS = 30                # disposition_requested == "return to service"; the rest go to storage
N_NOTE_MISMATCH = 20      # a reviewer note written in the register that contradicts the record

# Invented holding locations. Never mapped by any field in src/select.py, so this section is the
# one a reader can point at and say "that is what selection did" -- it is never sent to a model.
LOCATIONS = [
    "Bonded store 12, North Bay",
    "Bonded store 4, East Annex",
    "Quarantine cage 2, Main Hangar",
    "Serviceable rack 31, South Store",
    "Receiving bay 7, West Dock",
    "Bonded store 19, Central Store",
]

# Synthetic airframe references. Two characters and two digits, no relation to any registration
# format any authority issues.
AIRFRAMES = ["AF-03", "AF-07", "AF-11", "AF-14", "AF-22", "AF-28", "AF-31", "AF-40", "AF-45"]

# Published life limits, as round pairs. Deliberately varied in which side is tighter, so
# "inside on hours and outside on cycles" is a natural outcome rather than a special case.
LIMIT_PAIRS = [
    (20000, 15000),
    (30000, 20000),
    (18000, 25000),
    (25000, 18000),
    (12000, 30000),
    (24000, 12000),
    (16000, 20000),
]

# Notes whose REGISTER says "this pack is fine". Used truthfully on a component the trail clears,
# and against type on one it does not -- half the planted ambiguity.
CALM_NOTES = [
    "Paperwork reads complete to me, nothing outstanding from records.",
    "Pack arrived tidy and in order; no follow-up raised at receipt.",
    "Routine file. Nothing here I would hold anyone up over.",
    "Trail looks continuous on a quick read, filed without comment.",
]

# Notes whose REGISTER says "something is wrong with this pack". Used truthfully on a component
# the trail does not clear, and against type on one it does -- the other half.
WORRIED_NOTES = [
    "Second reviewer asked for this pack to be looked at again before anyone signs it.",
    "Escalated at last audit for an unresolved paperwork query; still open as far as I know.",
    "Not comfortable with this file yet, would want a supervisor over it first.",
    "Flagged during the last records sweep and never properly closed out.",
]

BASE_YEAR = 2014


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


def life_status(trail_hours, trail_cycles, limit_hours, limit_cycles, record_gap):
    """THE RULE, in one place. src/extract.py::life_status() is the same function, run over the
    MODEL's own extracted figures; data/fields.json and src/prompt.py state it to the model in
    words. Three readers, one definition, so the corpus, the prompt and the scorer cannot drift
    apart about what "past its limit" means.

    Returns one of the five allowed values, or None when a figure the rule needs is missing or
    malformed. An unknown is not a pass.

    ⚠︎ THE EXCEEDANCE CHECKS RUN BEFORE THE GAP CHECK, ON PURPOSE. A missing period can only add
    accumulated life, so it cannot rescue a component the surviving records already put at or past
    a limit. The gap only makes "within limits" undeterminable.

    ⚠︎ THE LIMIT IS INCLUSIVE: at exactly the published limit there is no life left.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED LIFE-LIMIT STRUCTURE AND ITS OWN CONVENTION FOR WHAT A
    RECORD TRAIL SUBSTANTIATES. No real airworthiness directive, maintenance manual or operator
    procedure was consulted and none is reproduced. It is a statement about the RECORDS. It is not
    an airworthiness determination, and nothing downstream of it releases anything to service.
    """
    nums = (trail_hours, trail_cycles, limit_hours, limit_cycles)
    for v in nums:
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
    if record_gap not in ("yes", "no"):
        return None
    hours_out = trail_hours >= limit_hours
    cycles_out = trail_cycles >= limit_cycles
    if hours_out and cycles_out:
        return "both_exceeded"
    if hours_out:
        return "hours_exceeded"
    if cycles_out:
        return "cycles_exceeded"
    if record_gap == "yes":
        return "cannot_determine"
    return "within_limits"


def tag_agreement(tag_hours, tag_cycles, trail_hours, trail_cycles):
    """"yes" / "no", or None when a figure the comparison needs is missing. Exact equality on both
    counters -- a tag that is right about hours and wrong about cycles does not agree."""
    vals = (tag_hours, tag_cycles, trail_hours, trail_cycles)
    for v in vals:
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
    return "yes" if (tag_hours == trail_hours and tag_cycles == trail_cycles) else "no"


def _split(rng, total, n):
    """Split a positive whole `total` into `n` positive whole parts, none of them tiny.
    Deterministic under the seeded RNG and exact by construction: the last part absorbs the
    rounding, so the parts always sum to `total`."""
    if n == 1:
        return [total]
    while True:
        weights = [rng.uniform(0.6, 1.4) for _ in range(n)]
        s = sum(weights)
        parts = [max(1, int(round(total * w / s))) for w in weights[:-1]]
        last = total - sum(parts)
        if last >= 1 and min(parts) >= max(1, total // (n * 6)):
            return parts + [last]


def _periods(rng, n, total_hours, total_cycles):
    """`n` installation periods whose hours sum to total_hours and whose cycles sum to
    total_cycles, with a DIFFERENT hours-per-cycle ratio on each one.

    ⚑ THE RATIOS ARE THE POINT. Each period ran on a different airframe flying a different average
    sector length, so hours and cycles have to be summed independently. A reader who takes one
    period's ratio and scales the cycles total off the hours total gets a wrong number every time.

    ⚠︎ THE SPREAD IS AROUND THE PACK'S OWN OVERALL RATIO, NOT AROUND A FIXED NUMBER. Different
    components in this corpus live on very different duty cycles -- one pack's whole trail can run
    at 0.8 hours a cycle and another's at 2.1 -- so a fixed band would have made the layout
    impossible for half of them. What is asserted is the SPREAD between periods within one pack,
    which is the property the trap depends on.
    """
    ratio = total_hours / float(total_cycles)
    for _attempt in range(600):
        cyc = _split(rng, total_cycles, n)
        hrs = []
        for c in cyc[:-1]:
            hrs.append(max(1, int(round(c * ratio * rng.uniform(0.72, 1.32)))))
        last = total_hours - sum(hrs)
        if last < 1:
            continue
        hrs.append(last)
        ratios = [h / float(c) for h, c in zip(hrs, cyc)]
        if min(ratios) < ratio * 0.60 or max(ratios) > ratio * 1.65:
            continue
        # Two periods at the same ratio would let a reader scale one off the other and be right.
        if len({round(r, 2) for r in ratios}) < n:
            continue
        return list(zip(hrs, cyc))
    raise RuntimeError("could not lay out %d periods over %d/%d" % (n, total_hours, total_cycles))


def _month_seq(rng, n_marks):
    """A rising sequence of YYYY-MM marks, wide enough apart to read as real service periods."""
    y, m = BASE_YEAR + rng.randint(0, 3), rng.randint(1, 12)
    out = []
    for _ in range(n_marks):
        out.append("%04d-%02d" % (y, m))
        step = rng.randint(4, 26)
        m += step
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
    return out


def _targets(rng, fault, limit_h, limit_c):
    """(trail_hours, trail_cycles) for one pack, from the fault mode and the published limits.

    The totals are chosen FIRST and the periods are laid out to hit them exactly, which is what
    lets a boundary case sit exactly ON the limit rather than near it.
    """
    def under(limit):
        return int(round(limit * rng.uniform(0.34, 0.86)))

    def over(limit):
        # Half the over-limit cases land EXACTLY on the published limit, on purpose --
        # inclusive means exceeded, and a reader treating the limit as exclusive gets them
        # backwards.
        if rng.random() < 0.50:
            return limit
        return int(round(limit * rng.uniform(1.01, 1.28)))

    if fault in ("clean", "gap_open"):
        return under(limit_h), under(limit_c)
    if fault == "hours_over":
        return over(limit_h), under(limit_c)
    if fault == "cycles_over":
        return under(limit_h), over(limit_c)
    if fault == "both_over":
        return over(limit_h), over(limit_c)
    if fault == "gap_over":
        # A declared gap AND a surviving total that is already past a limit. Which side is past is
        # dealt so the class is not always the same one.
        shape = rng.choice(["hours", "cycles", "both"])
        if shape == "hours":
            return over(limit_h), under(limit_c)
        if shape == "cycles":
            return under(limit_h), over(limit_c)
        return over(limit_h), over(limit_c)
    raise ValueError(fault)


def _tag_figures(rng, trail_h, trail_c, agrees, has_gap):
    """The figures written on the component's own tag.

    When they disagree with the trail they disagree for a reason a records reviewer would
    recognise: on a pack with a declared gap the tag carries an estimate for the missing period
    (so it reads HIGH against what the records substantiate); on a pack with no gap it is a
    transcription error, which can land either way and sometimes on one counter only.
    """
    if agrees:
        return trail_h, trail_c
    if has_gap:
        return trail_h + rng.randint(120, 1400), trail_c + rng.randint(90, 1100)
    which = rng.choice(["both", "hours", "cycles"])
    sign = rng.choice([1, -1])
    dh = rng.randint(40, 900) * sign if which in ("both", "hours") else 0
    dc = rng.randint(30, 700) * rng.choice([1, -1]) if which in ("both", "cycles") else 0
    return max(1, trail_h + dh), max(1, trail_c + dc)


def build_all(rng, n=N_RECORDS):
    stats = {"faults": {name: 0 for name, _ in FAULTS}, "status": {}, "gap": 0,
             "tag_mismatch": 0, "overhaul": 0, "note_mismatch": 0, "escalate": 0,
             "on_boundary": 0}

    faults = _deal(rng, n, FAULTS)
    tag_bad = _deal(rng, n, [(True, N_TAG_MISMATCH), (False, n - N_TAG_MISMATCH)])
    overhauls = _deal(rng, n, [(True, N_OVERHAUL), (False, n - N_OVERHAUL)])
    rts = _deal(rng, n, [("return to service", N_RTS),
                         ("shelf storage", n - N_RTS)])
    note_bad = _deal(rng, n, [(True, N_NOTE_MISMATCH), (False, n - N_NOTE_MISMATCH)])

    out = []
    for i in range(1, n + 1):
        fault = faults[i - 1]
        has_gap = fault in ("gap_open", "gap_over")
        limit_h, limit_c = rng.choice(LIMIT_PAIRS)
        trail_h, trail_c = _targets(rng, fault, limit_h, limit_c)

        n_periods = rng.randint(2, 4)
        periods = _periods(rng, n_periods, trail_h, trail_c)

        # Dates: two marks per installation period, plus one for the gap and one for an overhaul.
        n_marks = 2 * n_periods + (2 if has_gap else 0) + (1 if overhauls[i - 1] else 0)
        marks = _month_seq(rng, n_marks)
        mi = 0

        frames = rng.sample(AIRFRAMES, n_periods + (1 if has_gap else 0))
        # Where the declared gap sits in the trail, and where an overhaul sits.
        gap_at = rng.randint(1, n_periods - 1) if has_gap else None
        oh_at = rng.randint(1, n_periods - 1) if overhauls[i - 1] else None

        lines, gap_ref = [], None
        for p in range(n_periods):
            if gap_at == p:
                a, b = marks[mi], marks[mi + 1]
                mi += 2
                gap_ref = "GS-%04d" % rng.randint(1000, 9989)
                lines.append("%s to %s  airframe %s  accrual NOT RECORDED - records not "
                             "available, gap statement %s" % (a, b, frames[n_periods], gap_ref))
            if oh_at == p:
                a = marks[mi]
                mi += 1
                lines.append("%s              overhaul completed - time since overhaul reset to "
                             "0 hours / 0 cycles; time since new is unaffected and keeps accruing"
                             % a)
            a, b = marks[mi], marks[mi + 1]
            mi += 2
            h, c = periods[p]
            lines.append("%s to %s  airframe %s  accrued %d hours / %d cycles"
                         % (a, b, frames[p], h, c))

        status = life_status(trail_h, trail_c, limit_h, limit_c, "yes" if has_gap else "no")
        tag_h, tag_c = _tag_figures(rng, trail_h, trail_c, not tag_bad[i - 1], has_gap)
        agrees = tag_agreement(tag_h, tag_c, trail_h, trail_c)

        cleared = (status == "within_limits") and (agrees == "yes")
        mismatched_note = note_bad[i - 1]
        calm = cleared if not mismatched_note else (not cleared)
        note = rng.choice(CALM_NOTES if calm else WORRIED_NOTES)

        disposition = rts[i - 1]

        rec_id = "REC-%04d" % i
        component_id = "CMP-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                          rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                          rng.randint(10000, 99999))
        part_reference = "LLP-%04d-%02d" % (rng.randint(1000, 9899), rng.randint(1, 89))

        text = "\n".join([
            _underline("Component"), component_id, "",
            _underline("Part Reference"), part_reference, "",
            _underline("Holding Location"), rng.choice(LOCATIONS), "",
            _underline("Published Life Limit"), "%d hours / %d cycles since new"
            % (limit_h, limit_c), "",
            _underline("Component Tag Figures"), "%d hours / %d cycles since new"
            % (tag_h, tag_c), "",
            _underline("Service Record Trail"), "\n".join(lines), "",
            _underline("Records Gap"),
            ("one period declared, gap statement %s - accrual for that period cannot be "
             "reconstructed" % gap_ref) if has_gap else "none declared", "",
            _underline("Disposition Requested"), disposition, "",
            _underline("Reviewer Note"), note, "",
        ]) + "\n"

        gold = {
            "rec_id": rec_id,
            "component_id": component_id,
            "part_reference": part_reference,
            "life_limit_hours": limit_h,
            "life_limit_cycles": limit_c,
            "tag_hours": tag_h,
            "tag_cycles": tag_c,
            "trail_hours": trail_h,
            "trail_cycles": trail_c,
            "record_gap": "yes" if has_gap else "no",
            "disposition_requested": disposition,
            "reviewer_note": note,
            "tag_agrees": agrees,
            "life_status": status,
        }
        out.append((rec_id, text, gold))

        stats["faults"][fault] += 1
        stats["status"][status] = stats["status"].get(status, 0) + 1
        stats["gap"] += 1 if has_gap else 0
        stats["tag_mismatch"] += 1 if agrees == "no" else 0
        stats["overhaul"] += 1 if oh_at is not None else 0
        stats["note_mismatch"] += 1 if mismatched_note else 0
        if trail_h == limit_h or trail_c == limit_c:
            stats["on_boundary"] += 1
        if (status != "within_limits" or agrees == "no") and disposition == "return to service":
            stats["escalate"] += 1
    return out, stats


def _verify(rows):
    """Every gold value must be readable off the document it labels, every derived label must be
    the document's own arithmetic, and no reviewer note may ever be evidence. A corpus whose labels
    are not recoverable from its own text is not a corpus, it is a second opinion."""
    for rec_id, text, gold in rows:
        for field in ("component_id", "part_reference", "disposition_requested", "reviewer_note"):
            assert gold[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        assert "%d hours / %d cycles" % (gold["life_limit_hours"], gold["life_limit_cycles"]) \
            in text, "%s: the published limit is not stated verbatim" % rec_id
        assert "%d hours / %d cycles" % (gold["tag_hours"], gold["tag_cycles"]) in text, \
            "%s: the tag figures are not stated verbatim" % rec_id

        # ⚑ THE TRAIL TOTAL IS THE SUM OF THE PERIODS THE DOCUMENT ACTUALLY STATES. Re-read here
        # off the text rather than trusted from the generator's own variables, because the whole
        # kit rests on that sum being recoverable by a reader with nothing but the page.
        import re
        got_h = got_c = 0
        for m in re.finditer(r"accrued (\d+) hours / (\d+) cycles", text):
            got_h += int(m.group(1))
            got_c += int(m.group(2))
        assert got_h == gold["trail_hours"] and got_c == gold["trail_cycles"], \
            "%s: the stated periods sum to %d/%d, gold says %d/%d" \
            % (rec_id, got_h, got_c, gold["trail_hours"], gold["trail_cycles"])

        want = life_status(gold["trail_hours"], gold["trail_cycles"], gold["life_limit_hours"],
                           gold["life_limit_cycles"], gold["record_gap"])
        assert want == gold["life_status"], \
            "%s: gold labels %s, its own figures say %s" % (rec_id, gold["life_status"], want)
        assert tag_agreement(gold["tag_hours"], gold["tag_cycles"], gold["trail_hours"],
                             gold["trail_cycles"]) == gold["tag_agrees"], \
            "%s: tag agreement label disagrees with its own figures" % rec_id

        assert ("accrual NOT RECORDED" in text) == (gold["record_gap"] == "yes"), \
            "%s: the declared gap and the trail disagree" % rec_id

        # ⚑ THE NOTE CAN NEVER BE EVIDENCE, ASSERTED RATHER THAN INTENDED. If a note ever carried a
        # figure or a status word, a reader leaning on it would sometimes be right by accident and
        # the planted ambiguity would stop measuring anything.
        low = gold["reviewer_note"].lower()
        assert not any(ch.isdigit() for ch in low), "%s: a reviewer note states a figure" % rec_id
        for word in ("hour", "cycle", "limit", "exceed", "within", "gap", "tag"):
            assert word not in low, "%s: a reviewer note states %r" % (rec_id, word)


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
    print("record packs: %d   bytes: %d" % (len(rows), total))
    print("faults: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["faults"].items()))
    print("life_status: %s" % "  ".join("%s=%d" % (k, v)
                                        for k, v in sorted(stats["status"].items())))
    print("%d pack(s) declare a records gap; %d sit exactly ON a published limit" %
          (stats["gap"], stats["on_boundary"]))
    print("%d tag(s) disagree with the reconstructed trail total" % stats["tag_mismatch"])
    print("%d pack(s) carry an overhaul line mid-trail" % stats["overhaul"])
    print("%d (%.0f%%) carry a reviewer note whose REGISTER contradicts the record"
          % (stats["note_mismatch"], 100.0 * stats["note_mismatch"] / len(rows)))
    print("%d pack(s) carry a discrepancy AND are up for return to service -- the escalate flag"
          % stats["escalate"])
    print("internal consistency check: PASSED (every gold value is readable off its own document, "
          "the trail total is the sum of the periods the document states, every derived label is "
          "that document's own arithmetic, and no reviewer note states a figure or a status word)")


if __name__ == "__main__":
    main()
