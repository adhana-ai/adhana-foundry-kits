"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                       # noqa: E402
from src import rulebook as RB                      # noqa: E402
from src.extract import compute as _compute         # noqa: E402
from src.extract import correct_deciding_identifier as _deciding_of   # noqa: E402
from src.extract import correct_verdict as _verdict_of                # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ SIX NULLABLE FIELDS, AND EACH NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   *_identifier_value   is null exactly where its own *_identifier_type is `none` -- the
#                        invariant below is checked in BOTH directions.
#   *_dob                is null where the sheet says the date of birth is not recorded (customer
#                        side) or not published (list side). A PARTIAL date is NOT null: "1978" is
#                        a stated fact, and the rulebook's answer to it is "not comparable", which
#                        is a different thing from "absent".
#   *_place_of_birth     same, for the place.
NULLABLE = {"customer_identifier_value", "listed_identifier_value", "customer_dob", "listed_dob",
            "customer_place_of_birth", "listed_place_of_birth"}

# Floors on each hard case. Each is a reading a careless adjudicator gets wrong, and each has to be
# MEASURED rather than anecdotal -- so each has a minimum below which the run is refused.
MIN_TRANSLIT = 4          # same party, transliterated name, weak fields disagreeing
MIN_ID_CONFLICT = 4       # different parties, everything else agreeing
MIN_PARTIAL_DOB = 4       # a partial date that cannot be compared
MIN_NO_SECONDARY = 4      # a common name with nothing comparable on either side
MIN_DIFFERENT_TYPES = 3   # two strong identifiers of DIFFERENT types
MIN_CONTRADICTING_NOTE = 15   # analyst notes whose register contradicts the rulebook

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def _decide(r):
    return RB.decide(r["customer_identifier_type"], r["customer_identifier_value"],
                     r["listed_identifier_type"], r["listed_identifier_value"],
                     r["customer_dob"], r["listed_dob"],
                     r["customer_place_of_birth"], r["listed_place_of_birth"])


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["alert_id_key"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate alert_id_key in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d alert(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no alert sheet: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for alert_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (alert_id, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only these are nullable in this corpus: %s"
                % (f["name"], n_null, ", ".join(sorted(NULLABLE))))

    # ⚑ THE NULLABILITY INVARIANT ON THE IDENTIFIERS, BOTH WAYS. `none` is a VALUE for the type
    # field, and a value with no type (or a type with no value) is a corpus defect, not a state.
    for side in ("customer", "listed"):
        for alert_id, r in sorted(by_id.items()):
            t = r["%s_identifier_type" % side]
            v = r["%s_identifier_value" % side]
            if (t == "none") != (v is None):
                bad("%s: %s identifier type %r and value %r disagree about whether one exists"
                    % (alert_id, side, t, v))
            if t != "none" and t not in RB.STRONG:
                bad("%s: %s identifier type %r is not a strong type the rulebook carries"
                    % (alert_id, side, t))

    # ⚑ GOLD MUST AGREE WITH ITS OWN RULEBOOK LOOKUP. This is the check that makes the whole kit
    # honest: the label is not a second opinion about how alike two records look, it is the lookup.
    disagree = [s for s, r in sorted(by_id.items()) if _verdict_of(r) != r.get("verdict")]
    if disagree:
        bad("%d gold row(s) label a verdict their own values do not produce: %s"
            % (len(disagree), disagree[:5]))
    disagree_d = [s for s, r in sorted(by_id.items())
                  if _deciding_of(r) != r.get("deciding_identifier")]
    if disagree_d:
        bad("%d gold row(s) name a deciding identifier their own values do not produce: %s"
            % (len(disagree_d), disagree_d[:5]))

    # ⚑ AND THE DECIDING IDENTIFIER MUST AGREE WITH THE VERDICT'S SHAPE, both ways: nothing
    # decides an undecidable alert, and something always decides a decided one.
    for s, r in sorted(by_id.items()):
        undecidable = r["verdict"] == "insufficient_information"
        if undecidable != (r["deciding_identifier"] == "none"):
            bad("%s: verdict %r and deciding_identifier %r disagree about whether anything on the "
                "file decided it" % (s, r["verdict"], r["deciding_identifier"]))

    # ---- THE FIVE HARD CASES, ASSERTED RATHER THAN TRUSTED -----------------------------------

    # 1. A strong identifier outranks every weak disagreement. Remove it and the sheet flips.
    translit = []
    for s, r in sorted(by_id.items()):
        shared = RB.strong_pair(r["customer_identifier_type"], r["listed_identifier_type"])
        if shared is None or r["verdict"] != "same_party":
            continue
        if r["customer_name"] == r["listed_name"]:
            continue
        weak_disagree = (r["customer_nationality"] != r["listed_nationality"])
        moderate_disagree = (r["customer_place_of_birth"] is not None
                             and r["listed_place_of_birth"] is not None
                             and r["customer_place_of_birth"] != r["listed_place_of_birth"])
        if not (weak_disagree and moderate_disagree):
            continue
        translit.append(s)
        without = RB.verdict_of("none", None, "none", None, r["customer_dob"], r["listed_dob"],
                                r["customer_place_of_birth"], r["listed_place_of_birth"])
        if without != "not_a_match":
            bad("%s: a same_party alert whose name, nationality AND place of birth all disagree "
                "must read not_a_match with the shared identifier hidden -- it reads %r"
                % (s, without))
    if len(translit) < MIN_TRANSLIT:
        bad("only %d alert(s) are the same party under a transliterated name with the nationality "
            "AND the place of birth disagreeing -- one strong identifier against several weak "
            "mismatches needs at least %d to be measured rather than anecdotal"
            % (len(translit), MIN_TRANSLIT))
    else:
        print("  info  %d alert(s) are the same party under a transliterated name, with the "
              "nationality and the place of birth both disagreeing" % len(translit))

    # 2. A conflicting strong identifier separates two records that agree on everything else.
    id_conflict = []
    for s, r in sorted(by_id.items()):
        shared = RB.strong_pair(r["customer_identifier_type"], r["listed_identifier_type"])
        if shared is None or r["verdict"] != "not_a_match":
            continue
        id_conflict.append(s)
        if r["deciding_identifier"] != shared:
            bad("%s: separated by a conflicting %s, yet gold names %r as the deciding identifier"
                % (s, shared, r["deciding_identifier"]))
        without = RB.verdict_of("none", None, "none", None, r["customer_dob"], r["listed_dob"],
                                r["customer_place_of_birth"], r["listed_place_of_birth"])
        if without != "same_party":
            bad("%s: the conflicting identifier must be the ONLY thing separating these records "
                "-- with it hidden the sheet reads %r, not same_party" % (s, without))
    if len(id_conflict) < MIN_ID_CONFLICT:
        bad("only %d alert(s) are separated by a conflicting strong identifier alone -- the case "
            "where every soft signal says 'same party' needs at least %d"
            % (len(id_conflict), MIN_ID_CONFLICT))
    else:
        print("  info  %d alert(s) are separated by a conflicting strong identifier alone, with "
              "everything else on the sheet agreeing" % len(id_conflict))

    # 3. A partial date of birth is a stated fact and is still not comparable.
    partial = []
    for s, r in sorted(by_id.items()):
        for key in ("customer_dob", "listed_dob"):
            v = r[key]
            if v is not None and not RB.is_full_date(v):
                partial.append(s)
                break
    partial = sorted(set(partial))
    undecided_by_partial = []
    for s in partial:
        r = by_id[s]
        if r["verdict"] != "insufficient_information":
            continue
        undecided_by_partial.append(s)
        completed = RB.verdict_of(r["customer_identifier_type"], r["customer_identifier_value"],
                                  r["listed_identifier_type"], r["listed_identifier_value"],
                                  r["customer_dob"], r["customer_dob"],
                                  r["customer_place_of_birth"], r["listed_place_of_birth"])
        if completed != "same_party":
            bad("%s: this alert is undecidable only because a date is partial -- completing it "
                "must produce same_party, and it produces %r" % (s, completed))
    if len(undecided_by_partial) < MIN_PARTIAL_DOB:
        bad("only %d alert(s) are undecidable because of a PARTIAL date of birth -- the case a "
            "reader most often scores as a match needs at least %d"
            % (len(undecided_by_partial), MIN_PARTIAL_DOB))
    else:
        print("  info  %d alert(s) are undecidable purely because a date of birth is partial "
              "(%d carry a partial date in total)" % (len(undecided_by_partial), len(partial)))

    # 4. A common name with nothing comparable on either tier.
    names = {}
    for s, r in by_id.items():
        names.setdefault(r["customer_name"], []).append(s)
    repeated = {k: v for k, v in names.items() if len(v) > 1}
    no_secondary = [s for s, r in sorted(by_id.items())
                    if r["verdict"] == "insufficient_information"
                    and RB.strong_pair(r["customer_identifier_type"],
                                       r["listed_identifier_type"]) is None
                    and not (RB.is_full_date(r["customer_dob"])
                             and RB.is_full_date(r["listed_dob"]))
                    and not (r["customer_place_of_birth"] and r["listed_place_of_birth"])]
    if len(no_secondary) < MIN_NO_SECONDARY:
        bad("only %d alert(s) carry a name and nothing comparable at all -- the commonest reason a "
            "screening desk cannot decide needs at least %d" % (len(no_secondary), MIN_NO_SECONDARY))
    else:
        print("  info  %d alert(s) carry a name and nothing comparable at all; %d name(s) appear "
              "on more than one alert" % (len(no_secondary), len(repeated)))

    # 5. Two strong identifiers of DIFFERENT types tell you nothing about each other.
    different_types = [s for s, r in sorted(by_id.items())
                       if r["customer_identifier_type"] != "none"
                       and r["listed_identifier_type"] != "none"
                       and r["customer_identifier_type"] != r["listed_identifier_type"]]
    for s in different_types:
        r = by_id[s]
        if RB.strong_pair(r["customer_identifier_type"], r["listed_identifier_type"]) is not None:
            bad("%s: two identifiers of different types must not form a comparable pair" % s)
    if len(different_types) < MIN_DIFFERENT_TYPES:
        bad("only %d alert(s) put two strong identifiers of DIFFERENT types side by side -- the "
            "trap that looks like corroboration and is not needs at least %d"
            % (len(different_types), MIN_DIFFERENT_TYPES))
    else:
        print("  info  %d alert(s) carry two strong identifiers of DIFFERENT types -- comparable "
              "to nothing, and the rule falls through as though neither existed"
              % len(different_types))

    # ---- NO GRADER MAY BE DEGENERATE ---------------------------------------------------------
    counts = {}
    for r in by_id.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    for v in RB.VERDICTS:
        if not counts.get(v):
            bad("gold has no %r rows -- the three-way verdict grader would be degenerate" % v)
    print("  info  verdicts: %s"
          % "  ".join("%s=%d" % (k, counts.get(k, 0)) for k in RB.VERDICTS))

    dcounts = {}
    for r in by_id.values():
        dcounts[r["deciding_identifier"]] = dcounts.get(r["deciding_identifier"], 0) + 1
    if len(dcounts) < 4:
        bad("gold names only %d distinct deciding identifiers (%s) -- a seven-value grader with "
            "three live classes is a smaller grader wearing a bigger label"
            % (len(dcounts), sorted(dcounts)))
    else:
        print("  info  deciding identifiers: %s"
              % "  ".join("%s=%d" % (k, v) for k, v in sorted(dcounts.items())))

    n_open = sum(1 for r in by_id.values() if r["verdict"] != "not_a_match")
    if n_open in (0, len(by_id)):
        bad("every alert has the same dismissible answer (%d of %d not dismissible) -- the "
            "confusion matrix this kit exists to publish would be degenerate" % (n_open, len(by_id)))
    else:
        print("  info  %d of %d alerts are NOT dismissible on the file" % (n_open, len(by_id)))

    n_flag = sum(1 for r in by_id.values()
                 if _compute({"verdict": r.get("verdict"),
                              "account_status": r.get("account_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code escalation flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d alerts are not dismissible AND already live -- the escalation flag"
              % (n_flag, len(by_id)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the lesson a sibling kit in this series paid for live: its
    # first keyword list fired on a negation inside a relaxed note and mis-registered four rows.
    # This corpus contains that exact trap on purpose: a CONFIDENT note reads "I am satisfied these
    # are the same party", and the dismissive phrase is the whole negated form "not the same party".
    try:
        from evals.baseline import DISMISSIVE_KEYWORDS, HEDGING_KEYWORDS
        from tools.build_corpus import NOTES_BY_REGISTER
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        def register(note):
            low = note.lower()
            if any(k in low for k in HEDGING_KEYWORDS):
                return "hedging"
            if any(k in low for k in DISMISSIVE_KEYWORDS):
                return "dismissive"
            return "confident"
        n_notes = 0
        for want, notes in sorted(NOTES_BY_REGISTER.items()):
            for note in notes:
                n_notes += 1
                got = register(note)
                if got != want:
                    bad("the free floor reads a %s note as %s -- %r" % (want, got, note))
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as, including the negation trap" % n_notes)

    # ⚑ AND THE CONTRADICTION RATE IS MEASURED, NOT DESIGNED. The note's register follows the
    # engine's name score, so how often it points the wrong way is an emergent property of the
    # corpus. It still has to clear a floor, or the free comparison would be measuring nothing.
    try:
        from evals.baseline import extract_one as _floor
        from tools.build_corpus import REGISTER_VERDICT      # noqa: F401
    except ImportError:
        pass
    else:
        contradicting = 0
        for s, r in by_id.items():
            got = _floor(EX.load_doc(s), fields)["fields"]["verdict"]["value"]
            if got != r["verdict"]:
                contradicting += 1
        if contradicting < MIN_CONTRADICTING_NOTE:
            bad("only %d alert(s) carry an analyst note whose register contradicts the rulebook "
                "verdict -- the free comparison needs at least %d to say anything"
                % (contradicting, MIN_CONTRADICTING_NOTE))
        else:
            print("  info  %d of %d alerts carry an analyst note whose register contradicts the "
                  "rulebook verdict (%.0f pct)"
                  % (contradicting, len(by_id), 100.0 * contradicting / len(by_id)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d alert(s), %d field(s), gold consistent with the corpus and with its "
          "own rulebook lookup" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
