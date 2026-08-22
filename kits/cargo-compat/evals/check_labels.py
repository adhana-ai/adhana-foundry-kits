"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                       # noqa: E402
from src import matrix as MX                        # noqa: E402
from src.extract import compute as _compute         # noqa: E402
from src.extract import correct_verdict as _verdict_of   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ TWO NULLABLE FIELDS, AND EACH NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   prior_cargo    is null exactly where the sheet says the prior cargo is NOT RECORDED -- and
#                  that is the whole `undetermined` class, so the invariant below is two-way.
#   two_back_cargo is null where the sheet says the tank was recertified and carried nothing
#                  before the prior cargo. That is a KNOWN state, not a missing one, and it is
#                  never on its own a reason to answer `undetermined`.
NULLABLE = {"prior_cargo", "two_back_cargo"}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["check_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate check_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d sheet(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no sheet: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for check_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (check_id, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only %s are nullable in this corpus"
                % (f["name"], n_null, " and ".join(sorted(NULLABLE))))

    # ⚑ EVERY CARGO NAME IN GOLD MUST BE ONE THE SHIPPED MATRIX CARRIES. A cargo the matrix has
    # never heard of would make the verdict `undetermined` for a reason the corpus never intended,
    # and it would do so silently.
    for check_id, r in sorted(by_id.items()):
        for key in ("prior_cargo", "two_back_cargo", "incoming_product"):
            v = r.get(key)
            if v is not None and MX.class_of(v) is None:
                bad("%s: %s=%r is not a cargo the shipped matrix carries" % (check_id, key, v))

    # ⚑ THE NULLABILITY INVARIANT, BOTH WAYS: a missing prior cargo is exactly the undetermined
    # class, and nothing else produces one on this corpus.
    wrong_undet = [s for s, r in by_id.items()
                   if (r.get("prior_cargo") is None) != (r.get("verdict") == "undetermined")]
    if wrong_undet:
        bad("%d row(s) where prior_cargo nullness and verdict=='undetermined' disagree: %s"
            % (len(wrong_undet), sorted(wrong_undet)[:5]))

    # ⚑ GOLD MUST AGREE WITH ITS OWN MATRIX LOOKUP. This is the check that makes the whole kit
    # honest: the label is not a second opinion about the inspector's note, it is the lookup.
    disagree = []
    for check_id, r in sorted(by_id.items()):
        if _verdict_of(r) != r.get("verdict"):
            disagree.append(check_id)
    if disagree:
        bad("%d gold row(s) label a verdict their own values do not produce: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ THE FOUR HARD CASES, ASSERTED RATHER THAN TRUSTED. Each is a reading a careless reader
    # gets wrong, and each has to be MEASURED rather than anecdotal, so each has a floor.
    methanol_food = [s for s, r in by_id.items()
                     if r.get("prior_cargo") == "methanol"
                     and r.get("incoming_grade") == "food_grade"]
    for s in methanol_food:
        if by_id[s]["verdict"] != "refuse":
            bad("%s: methanol before a food-grade load must be refused, gold says %r"
                % (s, by_id[s]["verdict"]))
    if len(methanol_food) < 3:
        bad("only %d row(s) put methanol before a food-grade load -- the sharpest case in the "
            "matrix (compatible, water-soluble, banned anyway) needs at least 3 to be measured "
            "rather than anecdotal" % len(methanol_food))
    else:
        print("  info  %d row(s) put methanol before a food-grade load -- compatible, washes out, "
              "banned" % len(methanol_food))

    cert_below_log = [s for s, r in by_id.items()
                      if MX.WASH_RANK[r["wash_performed"]]
                      > MX.WASH_RANK[MX.certified_wash(r["wash_certified_for"])]]
    for s in cert_below_log:
        r = by_id[s]
        if r["verdict"] == "accept":
            bad("%s: the certificate covers less than the log claims, yet gold says accept" % s)
    if len(cert_below_log) < 3:
        bad("only %d row(s) have a certificate covering LESS than the tank log claims -- the "
            "wrong-wash-certificate trap needs at least 3" % len(cert_below_log))
    else:
        print("  info  %d row(s) carry a certificate covering LESS than the tank log claims was "
              "performed" % len(cert_below_log))

    two_back_only = []
    for s, r in by_id.items():
        tb = r.get("two_back_cargo")
        if tb is None or r.get("prior_cargo") is None:
            continue
        grade = r["incoming_grade"]
        if (MX.is_banned_predecessor(tb, grade)
                and not MX.is_banned_predecessor(r["prior_cargo"], grade)
                and not MX.is_reactive(r["prior_cargo"], r["incoming_product"])):
            two_back_only.append(s)
            without = MX.required_action(r["incoming_product"], grade, r["prior_cargo"], None,
                                         r["wash_certified_for"])
            if r["verdict"] != "refuse" or without != "accept":
                bad("%s: a banned two-back cargo must refuse, and must read as accept without it "
                    "(gold %r, without two-back %r)" % (s, r["verdict"], without))
    if len(two_back_only) < 3:
        bad("only %d row(s) are refused ONLY because of the cargo two back -- the look-back-depth "
            "case needs at least 3" % len(two_back_only))
    else:
        print("  info  %d row(s) are refused ONLY because of the cargo two back" % len(two_back_only))

    alarming_fine = [s for s, r in by_id.items()
                     if r.get("prior_cargo") is not None
                     and MX.class_of(r["prior_cargo"]) in ("caustic", "acid", "oxidiser")
                     and r["verdict"] == "accept"]
    if len(alarming_fine) < 3:
        bad("only %d row(s) pair an alarming-sounding corrosive heel with an accept verdict -- "
            "the looks-bad-is-fine case needs at least 3" % len(alarming_fine))
    else:
        print("  info  %d row(s) clear a corrosive heel that sounds alarming and rinses out"
              % len(alarming_fine))

    # ⚑ NO GRADER MAY BE DEGENERATE. A verdict class with no members, or a hold flag that is
    # constant, would score perfectly and mean nothing.
    counts = {}
    for r in by_id.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    for v in MX.VERDICTS:
        if not counts.get(v):
            bad("gold has no %r rows -- the four-way verdict grader would be degenerate" % v)
    print("  info  verdicts: %s"
          % "  ".join("%s=%d" % (k, counts.get(k, 0)) for k in MX.VERDICTS))

    n_blocked = sum(1 for r in by_id.values() if r["verdict"] != "accept")
    if n_blocked in (0, len(by_id)):
        bad("every sheet has the same clear-to-load answer (%d of %d blocked) -- the safety "
            "matrix this kit exists to publish would be degenerate" % (n_blocked, len(by_id)))
    else:
        print("  info  %d of %d sheets must NOT be loaded as they stand" % (n_blocked, len(by_id)))

    n_flag = sum(1 for r in by_id.values()
                 if _compute({"verdict": r.get("verdict"), "load_status": r.get("load_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code hold flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d sheets are not clear-to-load AND already loaded -- the hold flag"
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
    print("check_labels: %d sheet(s), %d field(s), gold consistent with the corpus and with its "
          "own matrix lookup" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
