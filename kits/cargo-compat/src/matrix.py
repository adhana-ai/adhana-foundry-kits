"""THE COMPATIBILITY MATRIX, loaded from data/matrix.json. Pure code, no model, no network.

⚑ THE MATRIX IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. The decision this kit makes is
a lookup over a compatibility table plus reasoning over a cleaning record, so the table has to be a
thing a reader can open, read, disagree with and replace -- not a dict buried in a Python module.
`data/matrix.json` is that file. Everything below is the arithmetic that reads it.

⚠︎ THE SHIPPED MATRIX IS ILLUSTRATIVE AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no commercial, industry-body or proprietary compatibility chart, no carrier's own
prior-cargo list and no regulatory schedule. It is not a substitute for the incoming product's
safety data sheet or for a competent person's assessment. See data/SOURCES.md, and the same
sentence is printed on the kit's own UI where a reader actually reads the verdict.

⚑ FOUR CHECKS, IN THIS ORDER, AND THE ORDER IS THE WHOLE DIFFICULTY:

  1. IS THE PRIOR CARGO EVEN KNOWN? An unknown or unrecorded prior cargo is `undetermined`. It is
     not `accept` and it is not `refuse` -- the kit names what it could not determine rather than
     inventing a verdict, because the only safe reading of a missing cleaning history is that
     nobody can say yet.
  2. REACTIVE PAIR. A heel that reacts with the incoming bulk is `refuse` outright. No cleaning
     regime in this matrix clears it, because the hazard is the residue itself.
  3. PREDECESSOR BAN, over the LOOK-BACK DEPTH the incoming grade asks for. Food grade and high
     purity look back TWO cargoes, not one. A ban is `refuse` and cleaning does not cure it --
     methanol before a food-grade load is the sharpest case in the matrix: chemically compatible,
     water-soluble, trivially washed out, and banned anyway.
  4. MINIMUM CERTIFIED WASH. Only what the CERTIFICATE names counts. The tank log's own
     "wash performed" line is never an input. Meet the minimum and the verdict is `accept`;
     fall short and it is `clean_then_load`, with the required regime named.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIX_PATH = os.path.join(HERE, "data", "matrix.json")

GRADES = ("technical", "food_grade", "high_purity")

VERDICTS = ("accept", "clean_then_load", "refuse", "undetermined")


def load(path=MATRIX_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


M = load()

WASH_LADDER = list(M["wash_ladder"])
WASH_RANK = {name: i for i, name in enumerate(WASH_LADDER)}

# cargo name -> class, built once from the class lists so there is exactly one spelling of the
# membership and no second table to drift from it.
CLASS_OF = {}
for _cls, _members in M["classes"].items():
    for _name in _members:
        CLASS_OF[_name] = _cls

CARGOES = sorted(CLASS_OF)

# Symmetric, so a caller never has to remember which way round to ask.
REACTIVE = set()
for _p in M["reactive_pairs"]:
    REACTIVE.add((_p["a"], _p["b"]))
    REACTIVE.add((_p["b"], _p["a"]))
REACTIVE_WHY = {}
for _p in M["reactive_pairs"]:
    REACTIVE_WHY[(_p["a"], _p["b"])] = _p["why"]
    REACTIVE_WHY[(_p["b"], _p["a"])] = _p["why"]


def class_of(cargo):
    """The matrix class for a cargo name, or None when the matrix does not carry it.

    None is a real answer here and it is deliberately NOT folded into "probably fine". A cargo the
    shipped matrix has never heard of is exactly the case a pre-load check must escalate, and
    `required_action` turns it into `undetermined` rather than guessing from the name.
    """
    if cargo in (None, ""):
        return None
    return CLASS_OF.get(str(cargo).strip().lower())


def is_reactive(prior_cargo, incoming_product):
    a, b = class_of(prior_cargo), class_of(incoming_product)
    if a is None or b is None:
        return False
    return (a, b) in REACTIVE


def reactive_reason(prior_cargo, incoming_product):
    return REACTIVE_WHY.get((class_of(prior_cargo), class_of(incoming_product)))


def is_banned_predecessor(cargo, grade):
    """Is this cargo barred from preceding a load of this grade, whatever the cleaning record says?"""
    if cargo in (None, ""):
        return False
    name = str(cargo).strip().lower()
    if name in {c.lower() for c in M["banned_predecessor_cargoes"].get(grade, [])}:
        return True
    return class_of(name) in set(M["banned_predecessor_classes"].get(grade, []))


def lookback(grade):
    """How many cargoes back the predecessor ban reads for this grade. 1 or 2."""
    return int(M["lookback"].get(grade, 1))


def minimum_wash(prior_cargo, grade):
    """The minimum wash the CERTIFICATE must name, or None when the class is unknown."""
    cls = class_of(prior_cargo)
    if cls is None or grade not in GRADES:
        return None
    base = WASH_RANK[M["minimum_wash"][cls]]
    rank = min(len(WASH_LADDER) - 1, base + int(M["grade_uplift"][grade]))
    return WASH_LADDER[rank]


def certified_wash(wash_certified_for):
    """What the tank is actually credited with.

    ⚠︎ THIS IS THE FUNCTION THE WHOLE `wash_performed` DECOY TURNS ON. The certificate governs. An
    uncertified tank is credited with `none` -- not with whatever the log line claims was done to
    it -- and a certificate naming a lower regime than the log claims is credited at the lower one.
    """
    if wash_certified_for in (None, "", "not_certified"):
        return "none"
    if wash_certified_for not in WASH_RANK:
        return None
    return wash_certified_for


def required_action(incoming_product, incoming_grade, prior_cargo, two_back_cargo,
                    wash_certified_for):
    """THE RULE, in one place, returning one of VERDICTS.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words, and evals/judge.py re-runs it over the model's OWN extracted
    values for the no-gold consistency diagnostic. They cannot drift about what a verdict means.

    ⚠︎ IT PROPOSES. IT NEVER AUTHORISES. The return value is a recommendation with a reason
    attached; a qualified person authorises the load. Nothing in this kit writes, dispatches or
    releases anything.
    """
    return decide(incoming_product, incoming_grade, prior_cargo, two_back_cargo,
                  wash_certified_for)["verdict"]


def decide(incoming_product, incoming_grade, prior_cargo, two_back_cargo, wash_certified_for):
    """The same rule, with its reasoning. {verdict, reason, required_wash, undetermined_because}.

    The reason string is what makes the verdict auditable by the person who has to sign the load
    off, and it is derived here rather than taken from the model -- a model-authored justification
    for a code-computed verdict is a caption, not evidence.
    """
    out = {"verdict": None, "reason": None, "required_wash": None, "undetermined_because": None}

    if incoming_grade not in GRADES:
        out["verdict"] = "undetermined"
        out["undetermined_because"] = "the incoming grade is missing or is not one this matrix carries"
        out["reason"] = out["undetermined_because"]
        return out

    if prior_cargo in (None, ""):
        out["verdict"] = "undetermined"
        out["undetermined_because"] = "the tank's prior cargo is not recorded"
        out["reason"] = ("No prior cargo is recorded for this tank, so there is nothing to check "
                         "the incoming product against. This is not a clearance.")
        return out

    if class_of(incoming_product) is None:
        out["verdict"] = "undetermined"
        out["undetermined_because"] = "the incoming product is not in the shipped matrix"
        out["reason"] = ("The incoming product is not carried by this matrix, so no compatibility "
                         "class can be looked up for it.")
        return out

    if class_of(prior_cargo) is None:
        out["verdict"] = "undetermined"
        out["undetermined_because"] = "the prior cargo is not in the shipped matrix"
        out["reason"] = ("The prior cargo is not carried by this matrix, so no compatibility class "
                         "can be looked up for it.")
        return out

    if is_reactive(prior_cargo, incoming_product):
        out["verdict"] = "refuse"
        out["reason"] = ("Reactive pair: %s residue with an incoming %s load. %s"
                         % (class_of(prior_cargo), class_of(incoming_product),
                            reactive_reason(prior_cargo, incoming_product)))
        return out

    chain = [prior_cargo]
    if lookback(incoming_grade) >= 2:
        if two_back_cargo not in (None, ""):
            if class_of(two_back_cargo) is None:
                out["verdict"] = "undetermined"
                out["undetermined_because"] = "the two-back cargo is not in the shipped matrix"
                out["reason"] = ("A %s load reads two cargoes back, and the cargo before the prior "
                                 "one is not carried by this matrix."
                                 % incoming_grade.replace("_", " "))
                return out
            chain.append(two_back_cargo)

    for i, cargo in enumerate(chain):
        if is_banned_predecessor(cargo, incoming_grade):
            where = "the prior cargo" if i == 0 else "the cargo before the prior one"
            out["verdict"] = "refuse"
            out["reason"] = ("Restricted predecessor: %s is barred before a %s load, and %s is %s. "
                             "A predecessor ban is not a cleaning problem and no cleaning regime "
                             "clears it."
                             % (cargo, incoming_grade.replace("_", " "), where, cargo))
            return out

    required = minimum_wash(prior_cargo, incoming_grade)
    credited = certified_wash(wash_certified_for)
    if required is None or credited is None:
        out["verdict"] = "undetermined"
        out["undetermined_because"] = "the cleaning certificate names a regime this matrix does not carry"
        out["reason"] = out["undetermined_because"]
        return out

    out["required_wash"] = required
    if WASH_RANK[credited] >= WASH_RANK[required]:
        out["verdict"] = "accept"
        out["reason"] = ("A %s heel before a %s load needs a certified %s; the certificate names "
                         "%s, which meets it."
                         % (class_of(prior_cargo), incoming_grade.replace("_", " "),
                            required, credited))
    else:
        out["verdict"] = "clean_then_load"
        out["reason"] = ("A %s heel before a %s load needs a certified %s; the tank is credited "
                         "with %s. Clean to the required regime and re-certify before loading."
                         % (class_of(prior_cargo), incoming_grade.replace("_", " "),
                            required, credited))
    return out
