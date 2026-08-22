"""THE RESTRICTION CHECKS, loaded from data/checks.json. Pure code, no model, no network.

⚑ THE CHECK SET IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. The decision this kit makes
is "does this proposed application sit inside the restrictions on this label" -- eight comparisons
in a fixed precedence order. So the eight have to be a thing a reader can open, read, disagree with
and replace, not a chain of `if` statements buried in a Python module. `data/checks.json` is that
file: each check names the label line it reads, the proposal line it compares against, the
comparison itself, and whether a breach means the application must not be made at all or must not
be made YET. Everything below is the interpreter that walks it.

⚠︎ THE SHIPPED CHECK SET IS ILLUSTRATIVE AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no real product label, no manufacturer's use instructions, no registration, no
approved-use database and no regulator's guidance. It is not a substitute for the approved label
for your product in your territory or for a qualified adviser. See data/SOURCES.md, and the same
sentence is printed on the kit's own UI where a reader actually reads the verdict.

⚑ THE WALK, AND WHY THE ORDER IS THE WHOLE DIFFICULTY:

  1. HARD BEFORE TIMING. Checks 1-5 are restrictions no amount of waiting cures -- the crop, the
     tank mix, the rate, the season count, the buffer. Checks 6-8 are intervals that have not
     elapsed YET. A case that breaches both is `outside_label`, not `wait_required`: telling a
     grower to wait a fortnight before making an application the label does not permit at all is
     the most expensive wrong answer this kit can give, and it is the answer a reader who stops at
     the first date they recognise arrives at.
  2. UNREADABLE STOPS THE WALK. A check whose label value or proposal value is not stated cannot
     be performed, and the walk stops there with `insufficient_information`, naming the restriction
     it could not read. It does NOT fall through to the checks below it -- you cannot skip past a
     restriction you were unable to read.
  3. NOT APPLICABLE IS NOT UNKNOWN. The re-treatment interval does not apply when no application
     has been made to this crop this season. The tank-mix prohibition does not apply when no mix is
     planned, or when the label prohibits none. Those checks are skipped and they PASS. Folding
     them in with the unreadable ones would turn "there is nothing to check" into "we could not
     check", which is a different and much less useful answer.
  4. EVERY LIMIT IS INCLUSIVE EXCEPT THE SEASON COUNT. A rate exactly on the maximum is inside the
     label. A pre-harvest interval of 35 days is met by exactly 35 days to harvest. But
     `maximum applications per season: 3` with three already made means this one would be the
     fourth, so that comparison is strictly-less-than and nothing else here is.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS_PATH = os.path.join(HERE, "data", "checks.json")

VERDICTS = ("within_label", "wait_required", "outside_label", "insufficient_information")

# `none` is the deciding restriction of a case where nothing decided against the proposal. It is a
# real value and not a blank: "every check passed" is an answer, and a null there would be
# indistinguishable from a reply that did not say.
NO_RESTRICTION = "none"


def load(path=CHECKS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


C = load()

CHECKS = sorted(C["checks"], key=lambda c: c["order"])
BY_ID = {c["id"]: c for c in CHECKS}
RESTRICTIONS = tuple([c["id"] for c in CHECKS] + [NO_RESTRICTION])
HARD = tuple(c["id"] for c in CHECKS if c["kind"] == "hard")
TIMING = tuple(c["id"] for c in CHECKS if c["kind"] == "timing")


def _num(v):
    """A number out of whatever the reply carried, or None. A string the model quoted ("2.5") is
    the same reading as the number it quoted -- refusing it would score a formatting difference as
    a misreading."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # Tolerate a unit the model copied along with the value ("2.5 L/ha", "24 hours").
    head = s.split()[0].rstrip(",")
    try:
        return float(head)
    except ValueError:
        return None


def _items(v):
    """A label's comma-separated list, lower-cased and trimmed. `none` is an empty list."""
    if v is None:
        return []
    s = str(v).strip().lower()
    if s in ("", "none", "not stated"):
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _one(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    return s or None


def _skipped(check, values):
    """Is this check NOT APPLICABLE to this case? Any one clause is enough."""
    for clause in check.get("skip_when") or []:
        got = values.get(clause["field"])
        want = clause["equals"]
        if isinstance(want, str):
            if _one(got) == want.lower():
                return True
        else:
            if _num(got) is not None and _num(got) == float(want):
                return True
    return False


def _readable(check, values):
    """Can this check be performed at all? Both sides have to carry a value."""
    lab = values.get(check["label_field"])
    prop = values.get(check["proposal_field"])
    if check["op"] in ("member_of", "not_member_of"):
        return _one(lab) is not None and _one(prop) is not None
    return _num(lab) is not None and _num(prop) is not None


def _passes(check, values):
    """True when the proposal satisfies this check. Only called when it is readable."""
    lab = values.get(check["label_field"])
    prop = values.get(check["proposal_field"])
    op = check["op"]
    if op == "member_of":
        return _one(prop) in _items(lab)
    if op == "not_member_of":
        return _one(prop) not in _items(lab)
    a, b = _num(prop), _num(lab)
    if op == "le":
        return a <= b
    if op == "lt":
        return a < b
    if op == "ge":
        return a >= b
    raise ValueError("unknown op %r in check %r" % (op, check["id"]))


def _fmt(v):
    """What a value looks like in a sentence. Trailing `.0` on a whole number is noise."""
    n = _num(v)
    if n is None:
        return str(v)
    if abs(n - round(n)) < 1e-9:
        return "%d" % round(n)
    return ("%g" % n)


def decide(values):
    """THE RULE, in one place. Returns {verdict, deciding_restriction, reason, checks}.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words (rendered from the same file, never retyped), and
    evals/judge.py re-runs it over the model's OWN extracted values for the no-gold consistency
    diagnostic. They cannot drift about what a verdict means or about which restriction decided it.

    ⚠︎ IT PROPOSES. IT NEVER AUTHORISES AN APPLICATION. The return value is a recommendation with
    its reasoning attached and a named restriction; a qualified adviser decides against the
    approved label. Nothing in this kit writes, dispatches, releases or clears anything.
    """
    trail = []
    for check in CHECKS:
        if _skipped(check, values):
            trail.append({"id": check["id"], "state": "not_applicable"})
            continue
        if not _readable(check, values):
            trail.append({"id": check["id"], "state": "not_stated"})
            return {
                "verdict": "insufficient_information",
                "deciding_restriction": check["id"],
                "reason": ("The %s is not stated, so this proposal cannot be checked against it. "
                           "That is not a clearance." % check["label_line"]),
                "checks": trail,
            }
        if _passes(check, values):
            trail.append({"id": check["id"], "state": "pass"})
            continue
        trail.append({"id": check["id"], "state": "breach"})
        return {
            "verdict": check["breach_verdict"],
            "deciding_restriction": check["id"],
            "reason": check["breach_says"].format(
                label=_fmt(values.get(check["label_field"])),
                proposal=_fmt(values.get(check["proposal_field"]))),
            "checks": trail,
        }
    return {
        "verdict": "within_label",
        "deciding_restriction": NO_RESTRICTION,
        "reason": ("Every applicable restriction on this label is satisfied by the proposal as it "
                   "stands. This is a reading of the label, not an authorisation."),
        "checks": trail,
    }


def verdict_of(values):
    """Just the verdict string, or None when the values are outside this kit's vocabulary."""
    v = decide(values)["verdict"]
    return v if v in VERDICTS else None


def restriction_of(values):
    """Just the deciding restriction, or None when it is outside this kit's vocabulary."""
    r = decide(values)["deciding_restriction"]
    return r if r in RESTRICTIONS else None
