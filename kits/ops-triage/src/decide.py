"""The page decision, and the five outcomes it can produce. Pure code, no model.

⚑ THE TWO MISTAKES DO NOT COST THE SAME AND THIS KIT NEVER AVERAGES THEM. A missed incident is an
outage nobody was told about: the cost is the whole of the downtime and it is discovered by a
customer. A false page is somebody woken at 3am for nothing: recoverable once, corrosive in bulk,
because enough of them is how a rotation learns to ignore the pager — which then produces the first
failure. Any single "accuracy" number hides which way the system fails, so this module returns both
counts and no combined figure, and `sweep()` exists so the report can show the trade instead of
asserting a winner.

⚑ WHY THERE ARE ONLY TWO VERDICTS, UNLIKE UC011's THREE. That kit offers `UNSURE` because a pair of
twins is genuinely unsettleable from the fields and handing it to a person is a real product
behaviour. A pager has no such state: at 03:14 the phone either rings or it does not, and an
"unsure" verdict would have to be mapped onto one of those two before anything happened. Mapping it
quietly — to `hold`, which is the tempting one, since it wakes nobody — would convert every
hesitation into a missed incident and hide it inside a calm-looking score. If a third state is ever
wanted here it has to be a real destination (a ticket, a morning queue), which is a product
decision and a different flow, not a word in a prompt.

THE FIVE OUTCOMES, and the reason each one is its own state:

    paged_correct     a real incident, and somebody was told
    missed_incident   an outage nobody was told about — THE EXPENSIVE DIRECTION, never averaged
    false_page        somebody woken for nothing — cheap once, expensive in bulk
    held_correct      noise, correctly left alone
    no_verdict        nothing usable came back from the model

⚠︎ `no_verdict` MUST NOT COLLAPSE INTO `held_correct`, AND THIS IS THE SUBTLEST TRAP IN THE KIT. A
model that returns nothing pages nobody, so a broken run LOOKS exactly like a calm night — quiet
pager, no false pages, an excellent-looking false-page number. Folding it into `held_correct` would
convert a total reliability failure into the best score the kit can produce. It is counted apart,
it is excluded from both published rates, and `answered` ships beside them so nobody can read a
rate without its denominator. UC011 published precision 100% / recall 100% off a single answered
pair in 78 before that rule existed.
"""
OUTCOMES = ("paged_correct", "missed_incident", "false_page", "held_correct", "no_verdict")

MEANS = {
    "paged_correct": "a real incident, and somebody was told",
    "missed_incident": "an outage nobody was told about — found by a customer",
    "false_page": "somebody woken for nothing — enough of these and the pager gets ignored",
    "held_correct": "noise, correctly left alone",
    "no_verdict": "nothing usable came back",
}

PAGE, HOLD = "PAGE", "HOLD"


def outcome(label, verdict, replied=True):
    """One window's outcome. `replied` is False when the model returned nothing usable."""
    if not replied or verdict not in (PAGE, HOLD):
        return "no_verdict"
    should = label == "page"
    if verdict == PAGE:
        return "paged_correct" if should else "false_page"
    return "missed_incident" if should else "held_correct"


def tally(rows):
    """Counts per outcome plus the two numbers, kept apart on purpose.

    ⚠︎ NO ACCURACY FIGURE IS RETURNED HERE AND THAT IS DELIBERATE. This corpus is 8% page, so
    "hold everything" scores 92% accurate while missing every incident in it. A single number on an
    unbalanced set is not a weak measurement, it is an actively misleading one — it rewards exactly
    the behaviour the kit exists to catch.

    `detection` is "of the incidents that were there, how many were paged" and its failures are
    MISSED INCIDENTS. `page_precision` is "of the pages sent, how many were real" and its failures
    are FALSE PAGES. Both are computed over answered windows only, and `answered` ships with them.
    """
    c = {k: 0 for k in OUTCOMES}
    for r in rows:
        c[r["outcome"]] = c.get(r["outcome"], 0) + 1
    paged = c["paged_correct"] + c["false_page"]
    real = c["paged_correct"] + c["missed_incident"]
    answered = len(rows) - c["no_verdict"]
    return {"counts": c, "windows": len(rows), "answered": answered,
            "coverage": round(answered / len(rows), 4) if rows else None,
            "detection": round(c["paged_correct"] / real, 4) if real else None,
            "page_precision": round(c["paged_correct"] / paged, 4) if paged else None,
            "missed_incidents": c["missed_incident"], "false_pages": c["false_page"],
            "no_verdict": c["no_verdict"],
            "reconciles": sum(c.values()) == len(rows)}


def by_trap(rows):
    """Per-trap results, because one number hides which KIND of hard case it fails — and here the
    kinds have different owners. Missing a `quiet-killer` is a prompt problem; paging on `flapping`
    is a threshold problem; missing `silence` means the window never carried the evidence at all."""
    out = {}
    for r in rows:
        t = out.setdefault(r["trap"], {"windows": 0, "wrong": 0, "outcomes": {}})
        t["windows"] += 1
        t["outcomes"][r["outcome"]] = t["outcomes"].get(r["outcome"], 0) + 1
        if r["outcome"] in ("missed_incident", "false_page", "no_verdict"):
            t["wrong"] += 1
    return out


def trap_verdict(rows):
    """Which trap KINDS a decider got completely right — the claim the wireframe makes.

    ⚑ THIS IS THE FUNCTION BEHIND "NO SETTING GETS ALL SIX RIGHT", so it returns the evidence
    rather than the sentence. A trap kind counts as handled only when every window carrying it came
    out correct; getting four of six flapping windows right is not "handles flapping", it is a
    coin flip with a good day. The claim is checked at every threshold in `sweep()` and it is
    allowed to come out false — if some setting ever does get all six, that is a finding and the
    report has to say so.
    """
    out = {}
    for trap, t in by_trap(rows).items():
        out[trap] = t["wrong"] == 0
    return out
