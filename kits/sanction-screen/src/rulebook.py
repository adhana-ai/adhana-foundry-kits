"""THE ADJUDICATION RULEBOOK, loaded from data/rulebook.json. Pure code, no model, no network.

⚑ THE RULEBOOK IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. Deciding whether a screening
alert and the watchlist entry it fired on are the same party is a comparison over identifiers with
a strength order, so the strength order has to be a thing a reader can open, read, disagree with
and replace -- not a dict buried in a Python module. `data/rulebook.json` is that file. Everything
below is the arithmetic that reads it.

⚠︎ THE SHIPPED RULEBOOK IS ILLUSTRATIVE AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no sanctions programme, no designation list, no supervisor's guidance, no industry
matching standard and no screening vendor's tuning, and it names no real list, authority,
programme, jurisdiction or person. See data/SOURCES.md, and the same sentence is printed on the
kit's own UI where a reader actually reads the answer.

⚠︎ IT ADJUDICATES ON PAPER AND NOTHING ELSE. This module clears nothing, blocks nothing and files
nothing. It returns a proposed verdict, the identifier that produced it, and -- when it cannot
decide -- what would settle it. A human makes the call.

⚑ FIVE CHECKS, IN THIS ORDER, AND THE ORDER IS THE WHOLE DIFFICULTY:

  1. STRONG IDENTIFIER, SAME VALUE -> same_party. A number issued to one party and no other,
     present on both records and equal, settles the alert. It outranks a different spelling of the
     name, a different nationality, a low engine score and even a conflicting place of birth. That
     is deliberately absolute, and it is the case a reader who reasons from "how similar do these
     two look" gets wrong.
  2. STRONG IDENTIFIER, DIFFERENT VALUE -> not_a_match. The same absoluteness pointing the other
     way: two different passport numbers separate two records whose name and full date of birth
     agree exactly.
  3. MODERATE CONFLICT -> not_a_match. With nothing strong to compare, one comparable moderate
     identifier that disagrees is enough.
  4. MODERATE AGREEMENT -> same_party, but only at `min_moderate_agreements` of them. Weak
     agreements never add up to a strong identifier.
  5. OTHERWISE -> insufficient_information, WITH A REASON. Not a failure to answer: a statement
     that these two records do not carry enough to be separated or joined.

⚑ COMPARABILITY IS THE SUBTLE PART, AND IT IS WHERE THE PARTIAL DATES LIVE. A year-only date of
birth is a STATED FACT, not a missing one -- and it is still not comparable, because it cannot
agree or disagree at the precision the rule needs. `_comparable_pair()` is the one place that
distinction is made, and it is why "1978" against "1978-04-12" contributes nothing rather than
counting as a match.

⚑ TWO STRONG IDENTIFIERS OF DIFFERENT TYPES ARE NOT COMPARABLE EITHER. A passport number on one
record and a national identity number on the other tell you nothing about each other; the rule
falls through to the moderate fields exactly as though neither record carried one.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULEBOOK_PATH = os.path.join(HERE, "data", "rulebook.json")


def load(path=RULEBOOK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


R = load()

VERDICTS = tuple(R["verdicts"])
STRONG = list(R["identifier_tiers"]["strong"])
MODERATE = list(R["identifier_tiers"]["moderate"])
WEAK = list(R["identifier_tiers"]["weak"])
MIN_MODERATE = int(R["min_moderate_agreements"])
LABELS = dict(R["identifier_labels"])

# The allowed values for the two identifier-type fields. `none` is a value, not an absence: a
# record that carries no strong identifier says so, and the field is never left blank.
IDENTIFIER_TYPES = tuple(STRONG) + ("none",)

# What `deciding_identifier` may be. Every verdict names one, and `none` is the honest answer for
# insufficient_information rather than a blank.
DECIDING = tuple(STRONG) + ("date_of_birth", "place_of_birth",
                            "date_of_birth_and_place_of_birth", "none")

# A full calendar date. Anything shorter -- "1978", "1978-04" -- is a stated fact and is NOT
# comparable. See `_comparable_pair`.
_FULL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def norm(v):
    """Trim, collapse whitespace, case-fold. Identifier values are compared on this and nothing
    fancier: a screening file that writes `TX 4820917` and `tx4820917` for the same number is a
    real thing, and `_norm_id` below handles that one separately."""
    if v in (None, ""):
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s.lower() or None


def _norm_id(v):
    """Identifier values ignore spaces, hyphens and case -- and NOTHING else.

    ⚠︎ DELIBERATELY NOT FUZZY. A transposed digit is a DIFFERENT identifier here, not a near miss,
    because the whole weight this rulebook puts on a strong identifier depends on it being exact.
    A rule that forgave one character would quietly turn check 2 into a similarity score.
    """
    s = norm(v)
    return re.sub(r"[\s\-]", "", s) if s else None


def is_full_date(v):
    s = norm(v)
    return bool(s and _FULL_DATE.match(s))


def _comparable_pair(field, a, b):
    """Is this moderate field comparable across the two records? -> True / False.

    The rulebook's `comparable` block states the rule in words; this is the same rule in code, and
    the two are read from one file so they cannot drift.
    """
    if field == "date_of_birth":
        return is_full_date(a) and is_full_date(b)
    return norm(a) is not None and norm(b) is not None


def strong_pair(customer_type, listed_type):
    """The strong identifier type both records carry, or None.

    None when either side has none, when either side's type is not a strong type this rulebook
    carries, or -- the case worth naming -- when the two sides carry DIFFERENT strong types. A
    passport number and a national identity number are two facts about two different registries.
    """
    a, b = norm(customer_type), norm(listed_type)
    if a is None or b is None or a != b:
        return None
    return a if a in STRONG else None


def decide(customer_identifier_type, customer_identifier_value,
           listed_identifier_type, listed_identifier_value,
           customer_dob, listed_dob,
           customer_place_of_birth, listed_place_of_birth):
    """THE RULE, in one place. {verdict, deciding_identifier, reason, would_settle_it}.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words, and evals/judge.py re-runs it over the model's OWN extracted
    values for the no-gold consistency diagnostic. They cannot drift about what a verdict means.

    ⚠︎ IT PROPOSES. IT CLEARS NOTHING, BLOCKS NOTHING AND FILES NOTHING. The return value is a
    recommendation with the deciding identifier attached; a human makes the call.
    """
    out = {"verdict": None, "deciding_identifier": None, "reason": None, "would_settle_it": None}

    shared = strong_pair(customer_identifier_type, listed_identifier_type)
    if shared is not None:
        cv, lv = _norm_id(customer_identifier_value), _norm_id(listed_identifier_value)
        if cv is not None and lv is not None:
            label = LABELS.get(shared, shared)
            out["deciding_identifier"] = shared
            if cv == lv:
                out["verdict"] = "same_party"
                out["reason"] = ("Both records carry the same %s. A strong identifier settles the "
                                 "alert in this rulebook and outranks every disagreement below it "
                                 "-- a different spelling of the name, a different nationality or "
                                 "a different place of birth does not overturn it." % label)
            else:
                out["verdict"] = "not_a_match"
                out["reason"] = ("Both records carry a %s and the two values are different. A "
                                 "strong identifier separates the parties in this rulebook even "
                                 "where the name and the full date of birth agree exactly." % label)
            return out

    # No strong identifier is comparable. Everything from here is the moderate tier.
    agree, conflict, not_comparable = [], [], []
    values = {"date_of_birth": (customer_dob, listed_dob),
              "place_of_birth": (customer_place_of_birth, listed_place_of_birth)}
    for field in MODERATE:
        a, b = values[field]
        if not _comparable_pair(field, a, b):
            not_comparable.append(field)
        elif norm(a) == norm(b):
            agree.append(field)
        else:
            conflict.append(field)

    if conflict:
        first = conflict[0]
        out["verdict"] = "not_a_match"
        out["deciding_identifier"] = first
        out["reason"] = ("No strong identifier is comparable across the two records, and the %s "
                         "does not agree. One conflicting moderate identifier separates them."
                         % LABELS.get(first, first))
        return out

    if len(agree) >= MIN_MODERATE:
        out["verdict"] = "same_party"
        out["deciding_identifier"] = ("date_of_birth_and_place_of_birth"
                                      if set(agree) == set(MODERATE) else agree[0])
        out["reason"] = ("No strong identifier is comparable, and %d moderate identifiers agree "
                         "with none conflicting -- %s. That meets this rulebook's threshold of %d."
                         % (len(agree), " and ".join(LABELS.get(f, f) for f in agree),
                            MIN_MODERATE))
        return out

    out["verdict"] = "insufficient_information"
    out["deciding_identifier"] = "none"
    out["reason"] = _undecided_reason(customer_identifier_type, listed_identifier_type,
                                      agree, not_comparable, customer_dob, listed_dob)
    out["would_settle_it"] = _would_settle_it(customer_identifier_type, listed_identifier_type,
                                              not_comparable)
    return out


def _undecided_reason(customer_identifier_type, listed_identifier_type, agree, not_comparable,
                      customer_dob, listed_dob):
    """Why the file cannot decide -- named, not shrugged at.

    ⚠︎ THIS IS THE STRING A READER ACTUALLY ACTS ON. "Insufficient information" with no reason is
    indistinguishable from a tool that fell over, and an adjudicator who cannot tell those apart
    will stop believing the third verdict entirely.
    """
    ct, lt = norm(customer_identifier_type), norm(listed_identifier_type)
    bits = []
    if ct in (None, "none") and lt in (None, "none"):
        bits.append("neither record carries a strong identifier")
    elif ct in (None, "none"):
        bits.append("the customer record carries no strong identifier")
    elif lt in (None, "none"):
        bits.append("the watchlist entry publishes no strong identifier")
    elif ct != lt:
        bits.append("the two records carry strong identifiers of DIFFERENT types (%s against %s), "
                    "which say nothing about each other"
                    % (LABELS.get(ct, ct), LABELS.get(lt, lt)))

    if "date_of_birth" in not_comparable:
        if norm(customer_dob) is None or norm(listed_dob) is None:
            bits.append("a date of birth is missing on one side")
        else:
            bits.append("one of the two dates of birth is partial, so the pair cannot be compared "
                        "at the precision this rulebook needs")
    if "place_of_birth" in not_comparable:
        bits.append("a place of birth is not stated on both records")

    tail = ("%d moderate identifier agrees, which is below the threshold of %d"
            % (len(agree), MIN_MODERATE)) if agree else "nothing comparable is left to weigh"
    return ("The file does not decide this alert: %s -- so %s. This is not a clearance and it is "
            "not a match; it is a statement that these two records do not carry enough to "
            "separate or join them." % ("; ".join(bits) if bits else "no identifier is comparable",
                                        tail))


def _would_settle_it(customer_identifier_type, listed_identifier_type, not_comparable):
    """What one extra fact would turn this alert into a decision. The whole value of naming
    `insufficient_information` is that it comes with the next step attached."""
    ct, lt = norm(customer_identifier_type), norm(listed_identifier_type)
    if ct not in (None, "none") and lt in (None, "none"):
        return ("a published %s on the watchlist entry, to compare against the one the customer "
                "record already carries" % LABELS.get(ct, ct))
    if lt not in (None, "none") and ct in (None, "none"):
        return ("a %s on the customer record, to compare against the one the watchlist entry "
                "already publishes" % LABELS.get(lt, lt))
    if ct not in (None, "none") and lt not in (None, "none") and ct != lt:
        return ("either record's %s, or the other's %s -- one identifier of the SAME type on both "
                "sides" % (LABELS.get(lt, lt), LABELS.get(ct, ct)))
    if "date_of_birth" in not_comparable:
        return "a full calendar date of birth on both records"
    if "place_of_birth" in not_comparable:
        return "a place of birth on both records"
    return "any strong identifier of the same type on both records"


def verdict_of(customer_identifier_type, customer_identifier_value,
               listed_identifier_type, listed_identifier_value,
               customer_dob, listed_dob, customer_place_of_birth, listed_place_of_birth):
    """Just the verdict string."""
    return decide(customer_identifier_type, customer_identifier_value,
                  listed_identifier_type, listed_identifier_value,
                  customer_dob, listed_dob,
                  customer_place_of_birth, listed_place_of_birth)["verdict"]
