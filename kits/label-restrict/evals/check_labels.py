"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import checks as CK                       # noqa: E402
from src import extract as EX                      # noqa: E402
from src.extract import compute as _compute        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ FIVE NULLABLE FIELDS, AND EACH NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   min_retreatment_interval_days / pre_harvest_interval_days / re_entry_interval_hours
#                                are null exactly where the label extract SAYS it does not state
#                                them -- which is the whole `insufficient_information` class on the
#                                label side.
#   days_since_last_application  is null where no application has been made to this crop this
#                                season. That is a KNOWN state, not a missing one, and it makes the
#                                re-treatment check NOT APPLICABLE rather than unreadable.
#   days_to_harvest              is null where the proposal omits it -- the other side of the page.
NULLABLE = {"min_retreatment_interval_days", "pre_harvest_interval_days",
            "re_entry_interval_hours", "days_since_last_application", "days_to_harvest"}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["case_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate case_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d case(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no case: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for case_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (case_id, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only %s are nullable in this corpus"
                % (f["name"], n_null, ", ".join(sorted(NULLABLE))))

    # ⚑ THE NULLABILITY INVARIANT ON THE ONE FIELD THAT IS A SKIP RATHER THAN A SILENCE.
    # days_since_last_application is null IF AND ONLY IF no application has been made this season.
    # If those two ever disagree, the re-treatment check is being skipped on a case that has a
    # value, or evaluated on one that does not -- and either way the corpus is lying about which
    # check fired.
    wrong_skip = [s for s, r in by_id.items()
                  if (r.get("days_since_last_application") is None)
                  != (r.get("applications_made_this_season") == 0)]
    if wrong_skip:
        bad("%d row(s) where days_since_last_application nullness and a zero season count "
            "disagree: %s" % (len(wrong_skip), sorted(wrong_skip)[:5]))

    # ⚑ GOLD MUST AGREE WITH ITS OWN WALK OF THE CHECK SET, ON BOTH ANSWERS. This is the check that
    # makes the whole kit honest: neither label is a second opinion about the agronomist's note.
    disagree_v = [s for s, r in by_id.items() if CK.verdict_of(r) != r.get("verdict")]
    if disagree_v:
        bad("%d gold row(s) label a verdict their own values do not produce: %s"
            % (len(disagree_v), disagree_v[:5]))
    disagree_r = [s for s, r in by_id.items()
                  if CK.restriction_of(r) != r.get("deciding_restriction")]
    if disagree_r:
        bad("%d gold row(s) label a deciding restriction their own values do not produce: %s"
            % (len(disagree_r), disagree_r[:5]))

    # ⚑ `none` AND `within_label` MUST AGREE IN BOTH DIRECTIONS. A `none` on a case that failed a
    # check would make the reason grader unscoreable on that row, silently.
    wrong_none = [s for s, r in by_id.items()
                  if (r.get("deciding_restriction") == CK.NO_RESTRICTION)
                  != (r.get("verdict") == "within_label")]
    if wrong_none:
        bad("%d row(s) where deciding_restriction=='none' and verdict=='within_label' disagree: %s"
            % (len(wrong_none), sorted(wrong_none)[:5]))

    # ⚑ THE HARD CASES, ASSERTED RATHER THAN TRUSTED. Each is a reading a careful person still gets
    # wrong, and each has to be MEASURED rather than anecdotal, so each has a floor.

    # 1. The off-by-one: the season maximum is a TOTAL, so "already made == maximum" is over it.
    season_at = [s for s, r in by_id.items()
                 if r.get("applications_made_this_season") == r.get("max_applications_per_season")]
    for s in season_at:
        if by_id[s]["verdict"] == "within_label":
            bad("%s: %s applications already made against a maximum of %s, yet gold says "
                "within_label" % (s, by_id[s]["applications_made_this_season"],
                                  by_id[s]["max_applications_per_season"]))
    if len(season_at) < 3:
        bad("only %d row(s) put the season count exactly ON the maximum -- the off-by-one needs "
            "at least 3 to be measured rather than anecdotal" % len(season_at))
    else:
        print("  info  %d row(s) have already used the whole season allowance -- this one would "
              "be the next" % len(season_at))

    # 2. Every limit is INCLUSIVE except that one. A case sitting exactly on the rate maximum, the
    #    buffer, the pre-harvest interval and the re-entry interval is INSIDE the label.
    at_limit = [s for s, r in by_id.items()
                if r.get("rate_proposed_l_per_ha") == r.get("max_rate_l_per_ha")
                and r.get("distance_to_water_m") == r.get("buffer_to_water_m")
                and r.get("days_to_harvest") == r.get("pre_harvest_interval_days")]
    for s in at_limit:
        if by_id[s]["verdict"] != "within_label":
            r = by_id[s]
            # Only a breach of some OTHER check may take it out of within_label.
            if r["deciding_restriction"] in ("max_rate_per_application", "buffer_to_water",
                                             "pre_harvest_interval"):
                bad("%s: every value sits exactly on an INCLUSIVE limit, yet gold blames %r"
                    % (s, r["deciding_restriction"]))
    if len(at_limit) < 3:
        bad("only %d row(s) sit exactly on three inclusive limits at once -- the "
            "looks-like-a-breach-and-is-not case needs at least 3" % len(at_limit))
    else:
        print("  info  %d row(s) sit exactly on the rate maximum, the buffer AND the pre-harvest "
              "interval -- all inclusive, all inside the label" % len(at_limit))

    # 3. The near-neighbour crop. A permitted list carrying the twin of the proposed crop.
    from tools.build_corpus import CROP_PAIRS
    twins = []
    for s, r in by_id.items():
        permitted = [c.strip() for c in (r.get("permitted_crops") or "").split(",")]
        here = r.get("crop_proposed")
        pair = next((p for p in CROP_PAIRS if here in p), None)
        if pair is None or here in permitted:
            continue
        twin = pair[1] if pair[0] == here else pair[0]
        if twin in permitted:
            twins.append(s)
            if r["verdict"] != "outside_label" or r["deciding_restriction"] != "permitted_crops":
                bad("%s: the label permits %r and the proposal is for %r, which must be "
                    "outside_label on permitted_crops (gold %r / %r)"
                    % (s, twin, here, r["verdict"], r["deciding_restriction"]))
    if len(twins) < 3:
        bad("only %d row(s) propose the NEAR NEIGHBOUR of a permitted crop -- the head-noun match "
            "needs at least 3" % len(twins))
    else:
        print("  info  %d row(s) propose a crop whose near neighbour IS on the label" % len(twins))

    # 4. Hard beats timing. A case breaching both must be outside_label on the hard restriction.
    both = []
    for s, r in by_id.items():
        d = CK.decide(r)
        breached = [c["id"] for c in d["checks"] if c["state"] == "breach"]
        if not breached:
            continue
        # Re-walk ignoring the hard checks, to see whether a timing one would ALSO have fired.
        timing_only = {k: v for k, v in r.items()}
        stopped_at = d["deciding_restriction"]
        if stopped_at not in CK.HARD:
            continue
        rest = _timing_breach(timing_only)
        if rest:
            both.append(s)
            if r["verdict"] != "outside_label":
                bad("%s: breaches the hard restriction %r AND the timing one %r, so it must be "
                    "outside_label (gold %r)" % (s, stopped_at, rest, r["verdict"]))
    if len(both) < 3:
        bad("only %d row(s) breach a hard restriction AND a timing one -- the precedence case, "
            "where 'wait a fortnight' is the most expensive wrong answer, needs at least 3"
            % len(both))
    else:
        print("  info  %d row(s) breach a HARD restriction and a TIMING one at once -- precedence "
              "decides, and the answer is not 'wait'" % len(both))

    # 5. The unit trap: the one restriction measured in hours.
    rei = [s for s, r in by_id.items() if r.get("deciding_restriction") == "re_entry_interval"]
    if len(rei) < 3:
        bad("only %d row(s) turn on the re-entry interval -- the only restriction on the label in "
            "HOURS, and the one this kit's reason grader exists to catch, needs at least 3"
            % len(rei))
    else:
        print("  info  %d row(s) turn on the re-entry interval, the only restriction in hours"
              % len(rei))

    # 6. The three confusable intervals must all be represented, or the reason grader is degenerate.
    for name in ("min_retreatment_interval", "pre_harvest_interval", "re_entry_interval"):
        n = sum(1 for r in by_id.values() if r.get("deciding_restriction") == name)
        if n < 3:
            bad("only %d row(s) turn on %s -- all three confusable intervals need at least 3 each "
                "or a right-verdict-wrong-reason error cannot be distinguished from noise"
                % (n, name))
    print("  info  deciding restrictions: %s"
          % "  ".join("%s=%d" % (k, sum(1 for r in by_id.values()
                                        if r.get("deciding_restriction") == k))
                      for k in CK.RESTRICTIONS))

    # 7. The previous-season decoy must actually be able to change an answer.
    #
    # ⚠︎ MEASURED BY RE-WALKING THE CHECK SET, NOT BY A PROXY -- and the proxy was written first
    # and was wrong in BOTH directions, which is why this comment exists. The obvious test is
    # "made < max AND made + previous > max", and on this corpus it counts 25 rows while the real
    # number is 26. It over-counts by 4, on rows where an EARLIER hard check already fires and the
    # season count never gets read. And it under-counts by 5, on rows where made == 0: adding a
    # previous season's applications there does not cross the maximum at all, it un-SKIPS the
    # re-treatment check -- whose skip clause is `applications_made_this_season is 0` -- and a
    # check that stops being not-applicable becomes unreadable, because days_since_last_application
    # is null on exactly those rows. So the decoy has a second mechanism nobody designed and the
    # proxy could not see. A rule this file exists to assert is a rule it must RUN, not approximate.
    would_flip = []
    for s, r in by_id.items():
        alt = dict(r)
        alt["applications_made_this_season"] = (r["applications_made_this_season"]
                                                + r["previous_season_applications"])
        d = CK.decide(alt)
        if (d["verdict"], d["deciding_restriction"]) != (r["verdict"],
                                                         r["deciding_restriction"]):
            would_flip.append(s)
    if len(would_flip) < 5:
        bad("only %d row(s) change answer if the PREVIOUS season's applications are added to this "
            "season's -- the decoy needs at least 5 to be measurable" % len(would_flip))
    else:
        n_within = sum(1 for s in would_flip if by_id[s]["verdict"] == "within_label")
        print("  info  %d row(s) change answer if the previous season's count is added in -- "
              "including all %d within_label rows, which all become outside_label. It is part of "
              "no check" % (len(would_flip), n_within))

    # ⚑ NO GRADER MAY BE DEGENERATE.
    counts = {}
    for r in by_id.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    for v in CK.VERDICTS:
        if not counts.get(v):
            bad("gold has no %r rows -- the four-way verdict grader would be degenerate" % v)
    print("  info  verdicts: %s" % "  ".join("%s=%d" % (k, counts.get(k, 0)) for k in CK.VERDICTS))

    n_stop = sum(1 for r in by_id.values() if r["verdict"] != "within_label")
    if n_stop in (0, len(by_id)):
        bad("every case has the same go-ahead answer (%d of %d stopped) -- the field-relevant "
            "binary this kit exists to publish would be degenerate" % (n_stop, len(by_id)))
    else:
        print("  info  %d of %d proposals must NOT be made as they stand" % (n_stop, len(by_id)))

    n_flag = sum(1 for r in by_id.values()
                 if _compute({"verdict": r.get("verdict"),
                              "application_status": r.get("application_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code hold flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d cases are outside the label AND already applied -- the hold flag"
              % (n_flag, len(by_id)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the lesson a sibling kit in this series paid for live: its
    # first keyword list fired on a negation inside a relaxed note and mis-registered four rows.
    try:
        from evals.baseline import WORRIED_KEYWORDS
        from tools.build_corpus import CALM_NOTES, WORRIED_NOTES
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        def worried(note):
            return any(k in note.lower() for k in WORRIED_KEYWORDS)
        for note in CALM_NOTES:
            if worried(note):
                bad("the free floor reads a CALM note as worried -- a keyword in %r fires on prose "
                    "that says the opposite: %r"
                    % ([k for k in WORRIED_KEYWORDS if k in note.lower()], note))
        for note in WORRIED_NOTES:
            if not worried(note):
                bad("the free floor reads a concerned note as calm -- no keyword matches: %r" % note)
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as" % (len(CALM_NOTES) + len(WORRIED_NOTES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d case(s), %d field(s), gold consistent with the corpus and with its own "
          "walk of data/checks.json -- verdict AND deciding restriction" % (len(docs), len(fields)))


def _timing_breach(values):
    """Would any TIMING check have fired on its own, ignoring the hard ones that stopped the walk?
    Used only to prove the precedence bucket is really a precedence bucket."""
    for c in CK.CHECKS:
        if c["kind"] != "timing":
            continue
        if CK._skipped(c, values) or not CK._readable(c, values):
            continue
        if not CK._passes(c, values):
            return c["id"]
    return None


if __name__ == "__main__":
    main()
