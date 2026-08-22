#!/usr/bin/env python3
"""Generate synthetic records-disposition review records and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one disposition review per file) and data/gold.jsonl, byte-identical on
every run. Every series id, custodian office, project name, hold id and records-officer note here
is invented -- nothing is fetched and nothing is licensed from anybody, so the corpus ships under
this repo's MIT licence. No real agency, real published retention schedule, real litigation matter
and no real person is named or reproduced. See data/SOURCES.md.

⚑ WHAT THIS KIT DECIDES, AND WHAT IT NEVER DOES. `disposition_eligible` says whether a record
series that has reached the end of its retention period may be PROPOSED for destruction, or
whether something still freezes it. It proposes; a records officer releases. Nothing in this kit
destroys, deletes or disposes of anything, and the guardrail downstream is the opposite of a
disposal action -- it pulls a series back OUT of a destruction queue.

⚑ GOLD `disposition_eligible` IS A DERIVATION, NOT A LABEL SOMEBODY TYPED. It is the same
priority-ordered rule the kit publishes everywhere else, run over the same structured values the
generator itself decided:

    1. a hold binds it            -> no   (an ACTIVE hold whose scope covers this record)
    2. an overlapping series      -> no   (a longer-retention series that has NOT yet expired)
    3. its own retention is open  -> no   (retention_expires is later than the review date)
    4. otherwise                  -> yes

It is never re-derived from the records officer's note, and the note never feeds the label.

⚑ THE HARD PART IS STEP 1, AND IT IS PROSE. A hold's scope is written the way a hold notice is
actually written -- "all correspondence relating to the Riverside project, 2019 onward" -- and has
to be judged against the record's OWN category, project and closed date. Four ways that goes wrong
are planted deliberately, in quantity, so each is measured rather than anecdotal:

  * PARTIAL COVERAGE BY CATEGORY -- the hold covers contracts, this series is correspondence.
  * PARTIAL COVERAGE BY PROJECT -- the hold names a different project.
  * A DATE RANGE THAT EXCLUDES THE RECORD -- the hold runs 2020 onward, the series closed 2019.
  * A RELEASED HOLD WITH A LIVE SUCCESSOR -- the covering hold says `released`, and a second,
    ACTIVE line continues its scope by reference. Reading the first line and stopping is wrong.
    So is treating every `released` line as a successor case: five records here carry a released
    hold that would have covered them and has NO successor, and those are eligible.

⚑ THE PLANTED AMBIGUITY: eligibility is structured, and the records officer's note disagrees with
it on `N_AMBIGUOUS` of records. A frozen series carries a breezy note ("Routine end-of-retention
item. Nothing outstanding on this series."); a genuinely eligible series carries a note that reads
as though something is wrong ("Escalated last cycle over a possible hold conflict -- pending
supervisor review."). Anything that classifies eligibility off the note's TONE -- including
evals/baseline.py's second floor, deliberately -- fails those records by construction.
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

# ⚑ ONE REVIEW DATE FOR THE WHOLE CORPUS, STATED EVERYWHERE. "Has this retention period elapsed?"
# is meaningless without a date to ask it on, and a per-record review date would be a twelfth
# thing for the model to read and a twelfth thing to get wrong for reasons that are not this
# kit's subject. So it is a constant: src/extract.py::AS_OF, src/prompt.py's rules, the field
# hints in data/fields.json and data/SOURCES.md all name the same "2026-08".
AS_OF = "2026-08"

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the same discipline the
# sibling kits in this series settled on after one generator asked for 40 pct ambiguity and
# delivered 51 pct. A count 1.7 standard deviations off its own design is not a corpus property,
# it is sampling noise being published as one.
#
# The five FROZEN classes and the five ELIGIBLE classes are named rather than counted into one
# bucket, because the whole question this kit asks is WHICH of them a reader gets wrong.
FROZEN_CLASSES = [
    ("hold_active", 10),        # an active hold whose scope covers this record outright
    ("hold_successor", 6),      # a released hold that covers, continued by an ACTIVE successor
    ("overlap_longer", 6),      # no binding hold; a longer-retention overlapping series is open
    ("retention_open", 6),      # its own retention period has not elapsed yet
]
ELIGIBLE_CLASSES = [
    ("scope_category_miss", 6),      # active hold, right project and dates, WRONG category
    ("scope_project_miss", 5),       # active hold, right category and dates, WRONG project
    ("scope_date_miss", 6),          # active hold, right category and project, dates exclude it
    ("released_no_successor", 5),    # a released hold that WOULD have covered; nothing follows it
    ("clear", 5),                    # no hold on file at all
]
N_AMBIGUOUS = 22                     # 40 pct, exactly -- an officer note from the wrong register
N_QUEUED = 30                        # already sitting in the destruction queue; the rest are not

CATEGORIES = ["correspondence", "contracts", "permits", "personnel", "financial"]

# ⚑ THE CATEGORY WORD A HOLD NOTICE WOULD USE, WHICH IS NOT ALWAYS THE FIELD VALUE. `financial`
# is a category code; a hold notice says "financial records". Writing the code straight into the
# scope prose produced "all financial relating to the Bell Harbor project" in the first build --
# not what a records officer would ever read, and the prose is the thing this kit asks a model to
# judge, so it has to read like the real artefact.
SCOPE_NOUNS = {
    "correspondence": "correspondence",
    "contracts": "contracts",
    "permits": "permits",
    "personnel": "personnel records",
    "financial": "financial records",
}

CATEGORY_TITLES = {
    "correspondence": "Project correspondence",
    "contracts": "Contract and procurement files",
    "permits": "Permit application files",
    "personnel": "Personnel action files",
    "financial": "Financial transaction files",
}

# Invented capital-project names. Nothing here is a real public works project.
PROJECTS = ["Riverside", "Northgate", "Fairview", "Cedar Hollow", "Milldam", "Bell Harbor"]

# Invented custodian offices. THIS IS THE SECTION NO FIELD MAPS TO -- see src/select.py. It is the
# one part of every record a reader can point at and say "selection left that out".
OFFICES = [
    "Silver Creek County Clerk",
    "Northgate Township Records Office",
    "Fairview Municipal Archives",
    "Cedar Hollow County Auditor",
    "Bell Harbor Port District Records",
    "Milldam Water Authority Records",
]

# ⚠︎ AN INVENTED GENERAL SCHEDULE, MODELLED ON THE PUBLIC SHAPE OF ONE. Real jurisdictions publish
# general records schedules as (item code, series description, retention period); that STRUCTURE is
# ordinary public-sector vocabulary. Every code and every period below was made up for this corpus
# and matches no published schedule anywhere.
SCHEDULES = [
    ("GS-01-04", "correspondence", 3),
    ("GS-05-08", "correspondence", 6),
    ("GS-11-02", "contracts", 7),
    ("GS-11-09", "contracts", 10),
    ("GS-17-03", "permits", 5),
    ("GS-22-06", "personnel", 7),
    ("GS-30-01", "financial", 7),
]

# A longer-retention series that captures the SAME records under a different item -- the second
# way a series that looks ripe is not. Also invented.
OVERLAPS = [
    ("GS-40-00", "Litigation case file", 20),
    ("GS-41-05", "Capital project master file", 25),
    ("GS-44-02", "Audit working papers", 10),
    ("GS-46-01", "Grant award file", 12),
]

HOLD_PREFIXES = [
    ("LH", "legal hold"),
    ("AH", "audit hold"),
    ("PR", "public-records request hold"),
]

# Notes whose TONE says "nothing is holding this series". Used truthfully on an eligible series,
# and against type on a frozen one -- half the planted ambiguity.
BREEZY_NOTES = [
    "Routine end-of-retention item. Nothing outstanding on this series.",
    "Standard disposition cycle. No open matters noted by this office.",
    "Clean series. The custodian confirms nothing further is expected here.",
    "Ordinary cycle item, no correspondence pending on it.",
]

# Notes whose TONE says "something is still holding this series". Used truthfully on a frozen
# series, and against type on one that is genuinely eligible -- the other half.
ANXIOUS_NOTES = [
    "Counsel asked us to take a second look at this one before anything moves.",
    "Escalated last cycle over a possible hold conflict -- pending supervisor review.",
    "The custodian was not confident this series is clear; flagged for manual audit.",
    "Disputed at intake. Something about this series looked off to the records committee.",
]


# --------------------------------------------------------------------------- dates

def ym(year, month):
    return "%04d-%02d" % (year, month)


def add_years(ym_str, years):
    """A retention period is expressed in whole years from the cutoff, so the month is carried
    through unchanged. Real date arithmetic on the pieces rather than string surgery -- adding
    years by pasting digits is how "20261-06" gets written."""
    y, m = (int(x) for x in ym_str.split("-"))
    return ym(y + years, m)


def expired(ym_str, as_of=AS_OF):
    """'YYYY-MM' sorts lexicographically iff it is zero-padded, which ym() guarantees."""
    return ym_str <= as_of


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs. Deterministic under
    the seeded RNG."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    assert len(out) == n, "class counts sum to %d, not %d" % (len(out), n)
    rng.shuffle(out)
    return out


# --------------------------------------------------------------------------- the rule

def scope_covers(scope, category, project, closed):
    """Does one hold's scope cover this record? Three independent tests, ALL of which must pass --
    which is exactly why partial coverage is the interesting failure: two of three passing looks
    like a match to anything reading quickly.

    `scope` is {categories, project, from_year, to_year}; `to_year` None means "onward".
    """
    if category not in scope["categories"]:
        return False
    if scope["project"] != "any" and scope["project"] != project:
        return False
    year = int(closed[:4])
    if year < scope["from_year"]:
        return False
    if scope["to_year"] is not None and year > scope["to_year"]:
        return False
    return True


def effective_scope(hold, holds):
    """A hold that continues another hold's scope by reference has no scope text of its own.
    Resolved ONE level and no further -- a chain would be a different corpus, and pretending to
    support one nobody wrote is how a rule quietly stops being the rule."""
    if hold.get("continues"):
        for other in holds:
            if other["id"] == hold["continues"]:
                return other["scope"]
        return None
    return hold["scope"]


def binding_hold_id(holds, category, project, closed):
    """The id of the ACTIVE hold that freezes this record, or None.

    Registry order, first match wins. A `released` line never binds on its own; it binds through
    the ACTIVE successor that continues its scope, and that successor is a registry line in its
    own right, so this single loop finds both cases.
    """
    for hold in holds:
        if hold["status"] != "active":
            continue
        scope = effective_scope(hold, holds)
        if scope and scope_covers(scope, category, project, closed):
            return hold["id"]
    return None


def eligibility(binding_hold, overlapping_expires, retention_expires, as_of=AS_OF):
    """THE RULE, collapsed to the three values a reply actually carries.

    src/extract.py::eligibility() is the same function, run over the MODEL's own extracted values;
    data/fields.json and src/prompt.py state it to the model in words. Three readers, one
    definition, so the corpus, the prompt and the guardrail cannot drift about what eligible means.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED DISPOSITION RULE, NOT ANY JURISDICTION'S. A real records
    programme weighs a filed general schedule, agency-specific items, an approved disposition
    authority, and a hold notice whose scope is negotiated with counsel. This is three conditions
    in a fixed order, chosen because it is the smallest rule that is genuinely useful and readable
    off one reply.
    """
    if binding_hold:
        return "no"
    if overlapping_expires is not None and not expired(overlapping_expires, as_of):
        return "no"
    if not expired(retention_expires, as_of):
        return "no"
    return "yes"


# --------------------------------------------------------------------------- generation

def _scope_prose(scope):
    cats = [SCOPE_NOUNS[c] for c in scope["categories"]]
    if len(cats) == 1:
        cat_phrase = "all %s" % cats[0]
    else:
        cat_phrase = "all %s and %s" % (", ".join(cats[:-1]), cats[-1])
    proj = ("relating to any project" if scope["project"] == "any"
            else "relating to the %s project" % scope["project"])
    if scope["to_year"] is None:
        span = "%d onward" % scope["from_year"]
    else:
        span = "%d to %d" % (scope["from_year"], scope["to_year"])
    return "%s %s, %s." % (cat_phrase, proj, span)


def _hold_id(rng, prefix, year):
    return "%s-%04d-%03d" % (prefix, year, rng.randint(1, 399))


def _covering_scope(rng, category, project, closed_year):
    """A scope that covers this record: its category is in the list, its project matches (or the
    hold is project-wide), and the range includes its closed year."""
    others = [c for c in CATEGORIES if c != category]
    rng.shuffle(others)
    cats = [category] + others[:rng.choice([0, 0, 1, 2])]
    rng.shuffle(cats)
    from_year = closed_year - rng.randint(0, 4)
    to_year = None if rng.random() < 0.6 else closed_year + rng.randint(0, 3)
    return {"categories": cats,
            "project": project if rng.random() < 0.7 else "any",
            "from_year": from_year, "to_year": to_year}


def _category_miss_scope(rng, category, project, closed_year):
    """Right project, right dates, WRONG category -- the hold is about the adjacent thing."""
    others = [c for c in CATEGORIES if c != category]
    rng.shuffle(others)
    cats = others[:rng.choice([1, 1, 2])]
    from_year = closed_year - rng.randint(0, 4)
    to_year = None if rng.random() < 0.6 else closed_year + rng.randint(0, 3)
    return {"categories": cats, "project": project,
            "from_year": from_year, "to_year": to_year}


def _project_miss_scope(rng, category, project, closed_year):
    """Right category, right dates, a DIFFERENT project named. Never 'any' -- a project-wide hold
    would cover, and this class exists to be the one that does not."""
    other = rng.choice([p for p in PROJECTS if p != project])
    from_year = closed_year - rng.randint(0, 4)
    to_year = None if rng.random() < 0.6 else closed_year + rng.randint(0, 3)
    return {"categories": [category], "project": other,
            "from_year": from_year, "to_year": to_year}


def _date_miss_scope(rng, category, project, closed_year):
    """Right category, right project, a range that EXCLUDES the record's closed year -- either
    the hold starts after the series closed, or it closed before the series did."""
    if rng.random() < 0.5:
        from_year = closed_year + rng.randint(1, 4)
        to_year = None if rng.random() < 0.5 else from_year + rng.randint(1, 5)
    else:
        to_year = closed_year - rng.randint(1, 4)
        from_year = to_year - rng.randint(1, 5)
    return {"categories": [category], "project": project,
            "from_year": from_year, "to_year": to_year}


def _noise_scope(rng, category, project, closed_year):
    """A hold that is on file and does not cover -- a wrong category AND a wrong project, so it
    cannot accidentally bind. Used to keep 'a hold is listed' from being a usable proxy for
    'this series is frozen', which is precisely the shortcut evals/baseline.py takes."""
    other_cat = rng.choice([c for c in CATEGORIES if c != category])
    other_proj = rng.choice([p for p in PROJECTS if p != project])
    from_year = closed_year - rng.randint(0, 6)
    to_year = None if rng.random() < 0.5 else closed_year + rng.randint(0, 3)
    return {"categories": [other_cat], "project": other_proj,
            "from_year": from_year, "to_year": to_year}


def _make_hold(rng, status, scope, closed_year, continues=None, year=None):
    """⚠︎ `year` IS AN ARGUMENT BECAUSE A SUCCESSOR CANNOT PREDATE WHAT IT SUCCEEDS. The first
    build drew both years independently and produced `PR-2022-041 | Continues: AH-2023-234` -- a
    hold that carried on a hold issued a year later. Nothing in the rule reads the year, so no
    assertion would ever have caught it; it is simply a record no records officer would believe,
    and the whole corpus rests on being believable."""
    prefix, _label = rng.choice(HOLD_PREFIXES)
    if year is None:
        year = min(2026, max(2016, closed_year + rng.randint(0, 5)))
    return {"id": _hold_id(rng, prefix, year), "status": status, "scope": scope,
            "continues": continues, "successor": None, "year": year}


def _registry_lines(holds):
    if not holds:
        return "none on file"
    out = []
    for h in holds:
        if h["continues"]:
            scope_text = "Scope: continues the scope of %s." % h["continues"]
            link = "Continues: %s" % h["continues"]
        else:
            scope_text = "Scope: %s" % _scope_prose(h["scope"])
            link = ("Superseded by: %s" % h["successor"]) if h["successor"] else "Successor: none"
        out.append("%s | %s | %s | %s" % (h["id"], h["status"], scope_text, link))
    return "\n".join(out)


def _pick_schedule(rng, category, want_open):
    """A schedule item for this category, plus a closed date whose retention has (or has not)
    elapsed by the review date. Returns (code, years, closed 'YYYY-MM', expires 'YYYY-MM')."""
    items = [s for s in SCHEDULES if s[1] == category]
    code, _cat, years = rng.choice(items)
    as_of_year = int(AS_OF[:4])
    for _attempt in range(40):
        if want_open:
            closed_year = rng.randint(as_of_year - years + 1, as_of_year - years + 5)
        else:
            closed_year = rng.randint(2006, as_of_year - years)
        closed = ym(closed_year, rng.randint(1, 12))
        exp = add_years(closed, years)
        if expired(exp) != want_open:
            return code, years, closed, exp
    raise AssertionError("could not place a %s retention for %r"
                         % ("live" if want_open else "elapsed", category))


def _pick_overlap(rng, closed, want_open):
    """An overlapping longer-retention series, or None. `want_open` True means it must still be
    live at the review date; False means it must already have elapsed, so it cannot freeze."""
    candidates = list(OVERLAPS)
    rng.shuffle(candidates)
    for code, title, years in candidates:
        exp = add_years(closed, years)
        if expired(exp) != want_open:
            return {"code": code, "title": title, "years": years, "expires": exp}
    return None


def build_one(rng, klass, index):
    category = rng.choice(CATEGORIES)
    project = rng.choice(PROJECTS)
    want_open_retention = (klass == "retention_open")
    code, years, closed, retention_expires = _pick_schedule(rng, category, want_open_retention)
    closed_year = int(closed[:4])

    # --- the overlapping series -------------------------------------------------------------
    if klass == "overlap_longer":
        overlap = _pick_overlap(rng, closed, want_open=True)
        assert overlap is not None, "overlap_longer needs a live overlapping series"
    elif rng.random() < 0.40:
        # An overlapping series that has ALREADY elapsed. On file, visible, and decides nothing --
        # the same shape as the one that freezes a record, so its presence is not a giveaway.
        overlap = _pick_overlap(rng, closed, want_open=False)
    else:
        overlap = None

    # --- the hold registry ------------------------------------------------------------------
    holds = []
    if klass == "hold_active":
        holds.append(_make_hold(rng, "active", _covering_scope(rng, category, project, closed_year),
                                closed_year))
    elif klass == "hold_successor":
        pred = _make_hold(rng, "released", _covering_scope(rng, category, project, closed_year),
                          closed_year)
        succ = _make_hold(rng, "active", None, closed_year, continues=pred["id"],
                          year=min(2026, pred["year"] + rng.randint(0, 2)))
        pred["successor"] = succ["id"]
        holds.extend([pred, succ])
    elif klass == "scope_category_miss":
        holds.append(_make_hold(rng, "active",
                                _category_miss_scope(rng, category, project, closed_year),
                                closed_year))
    elif klass == "scope_project_miss":
        holds.append(_make_hold(rng, "active",
                                _project_miss_scope(rng, category, project, closed_year),
                                closed_year))
    elif klass == "scope_date_miss":
        holds.append(_make_hold(rng, "active",
                                _date_miss_scope(rng, category, project, closed_year),
                                closed_year))
    elif klass == "released_no_successor":
        holds.append(_make_hold(rng, "released",
                                _covering_scope(rng, category, project, closed_year),
                                closed_year))
    elif klass == "clear":
        holds = []
    # overlap_longer and retention_open get a non-covering hold about half the time, so that
    # "the registry is empty" is not a usable proxy for "nothing else freezes this either".
    if klass in ("overlap_longer", "retention_open") and rng.random() < 0.5:
        holds.append(_make_hold(rng, rng.choice(["active", "released"]),
                                _noise_scope(rng, category, project, closed_year), closed_year))

    if len(holds) > 1:
        # Registry order is not authored order. The successor pair is shuffled too, so the ACTIVE
        # line is as often above the released one as below it.
        rng.shuffle(holds)

    bound = binding_hold_id(holds, category, project, closed)
    overlap_expires = overlap["expires"] if overlap else None
    verdict = eligibility(bound, overlap_expires, retention_expires)

    return {
        "klass": klass, "category": category, "project": project, "code": code,
        "years": years, "closed": closed, "retention_expires": retention_expires,
        "overlap": overlap, "holds": holds, "binding": bound, "eligible": verdict,
        "office": rng.choice(OFFICES),
        "series_id": "RS-%d-%04d" % (closed_year, rng.randint(100, 9999)),
        "title": "%s - %s" % (CATEGORY_TITLES[category], project),
    }


def render(rec, queue_status, note):
    if rec["overlap"]:
        overlap_line = "%s %s, %d years, expires %s" % (
            rec["overlap"]["code"], rec["overlap"]["title"], rec["overlap"]["years"],
            rec["overlap"]["expires"])
    else:
        overlap_line = "none on file"
    lines = [
        _underline("Record Series"), rec["series_id"], "",
        _underline("Custodian Office"), rec["office"], "",
        _underline("Series Title"), rec["title"], "",
        _underline("Record Category"), rec["category"], "",
        _underline("Related Project"), rec["project"], "",
        _underline("Record Closed"), rec["closed"], "",
        _underline("Retention Schedule"), "%s, %d years" % (rec["code"], rec["years"]), "",
        _underline("Retention Expires"), rec["retention_expires"], "",
        _underline("Overlapping Series"), overlap_line, "",
        _underline("Hold Registry"), _registry_lines(rec["holds"]), "",
        _underline("Disposition Queue"), queue_status, "",
        _underline("Officer Notes"), note, "",
    ]
    return "\n".join(lines) + "\n"


def build_all(rng, n=N_RECORDS):
    classes = _deal(rng, n, FROZEN_CLASSES + ELIGIBLE_CLASSES)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    queued = _deal(rng, n, [("queued", N_QUEUED), ("not_queued", n - N_QUEUED)])

    stats = {"eligible": 0, "frozen": 0, "ambiguous": 0, "needs_review": 0,
             "holds_on_file": 0, "overlap_on_file": 0,
             "classes": {k: 0 for k, _ in FROZEN_CLASSES + ELIGIBLE_CLASSES}}

    out = []
    for i in range(1, n + 1):
        klass = classes[i - 1]
        rec = build_one(rng, klass, i)
        stats["classes"][klass] += 1
        stats["eligible" if rec["eligible"] == "yes" else "frozen"] += 1
        if rec["holds"]:
            stats["holds_on_file"] += 1
        if rec["overlap"]:
            stats["overlap_on_file"] += 1

        queue_status = queued[i - 1]
        if rec["eligible"] == "no" and queue_status == "queued":
            stats["needs_review"] += 1

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the verdict normally, and contradicts it when ambiguous.
        breezy = (rec["eligible"] == "yes") if not ambiguous else (rec["eligible"] == "no")
        note = rng.choice(BREEZY_NOTES if breezy else ANXIOUS_NOTES)

        case_id = "RDS-%04d" % i
        text = render(rec, queue_status, note)
        gold = {
            "case_id": case_id,
            "series_id": rec["series_id"],
            "series_title": rec["title"],
            "record_category": rec["category"],
            "related_project": rec["project"],
            "record_closed": rec["closed"],
            "retention_code": rec["code"],
            "retention_expires": rec["retention_expires"],
            "overlapping_expires": rec["overlap"]["expires"] if rec["overlap"] else None,
            "binding_hold_id": rec["binding"],
            "queue_status": queue_status,
            "officer_notes": note,
            "disposition_eligible": rec["eligible"],
            "_class": klass,
        }
        out.append((case_id, text, gold, rec))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, and every gold verdict must be
    the derivation that document's own values produce. A corpus whose labels are not readable off
    its own text is not a corpus, it is a second opinion."""
    for case_id, text, gold, rec in rows:
        for field in ("series_id", "series_title", "record_category", "related_project",
                      "record_closed", "retention_code", "retention_expires", "queue_status",
                      "officer_notes"):
            assert gold[field] in text, "%s: %s not stated in the document" % (case_id, field)

        if gold["overlapping_expires"] is None:
            assert "none on file" in text, "%s: absent overlap not stated" % case_id
        else:
            assert gold["overlapping_expires"] in text, \
                "%s: overlapping_expires not stated verbatim" % case_id

        if gold["binding_hold_id"] is None:
            assert not any(h["id"] == gold["binding_hold_id"] for h in rec["holds"]), case_id
        else:
            assert gold["binding_hold_id"] in text, \
                "%s: binding_hold_id not stated verbatim" % case_id
            match = [h for h in rec["holds"] if h["id"] == gold["binding_hold_id"]]
            assert match and match[0]["status"] == "active", \
                "%s: the binding hold is not an ACTIVE registry line" % case_id

        want = eligibility(gold["binding_hold_id"], gold["overlapping_expires"],
                           gold["retention_expires"])
        assert gold["disposition_eligible"] == want, \
            "%s: gold verdict disagrees with its own values (rule says %s)" % (case_id, want)

        # The class labels are the corpus's own claim about WHY each record is what it is; a class
        # that quietly produced the wrong verdict would make every per-class number meaningless.
        klass = gold["_class"]
        if klass in dict(FROZEN_CLASSES):
            assert want == "no", "%s: %s produced an ELIGIBLE record" % (case_id, klass)
        else:
            assert want == "yes", "%s: %s produced a FROZEN record" % (case_id, klass)
        if klass in ("hold_active", "hold_successor"):
            assert gold["binding_hold_id"] is not None, "%s: %s bound nothing" % (case_id, klass)
        if klass in ("scope_category_miss", "scope_project_miss", "scope_date_miss",
                     "released_no_successor"):
            assert rec["holds"], "%s: %s has an empty registry" % (case_id, klass)
            assert gold["binding_hold_id"] is None, "%s: %s bound a hold" % (case_id, klass)
        if klass == "clear":
            assert not rec["holds"], "%s: clear has a hold on file" % case_id
        if klass == "hold_successor":
            cont = [h for h in rec["holds"] if h["continues"]]
            assert cont, "%s: hold_successor has no continuing line" % case_id
            pred = [h for h in rec["holds"] if h["id"] == cont[0]["continues"]]
            assert pred, "%s: the continuing line points at no registry entry" % case_id
            assert cont[0]["year"] >= pred[0]["year"], \
                "%s: a successor hold predates the hold it continues" % case_id

        for part in gold["record_closed"], gold["retention_expires"]:
            month = int(part.split("-")[1])
            assert 1 <= month <= 12, "%s: month out of range in %r" % (case_id, part)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_RECORDS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)
    _verify(rows)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for case_id, text, _gold, _rec in rows:
        with open(os.path.join(CORPUS, "%s.txt" % case_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _case_id, _text, gold, _rec in rows:
            fh.write(json.dumps(gold) + "\n")

    total = sum(len(t.encode("utf-8")) for _i, t, _g, _r in rows)
    print("records: %d   eligible: %d   frozen: %d   bytes: %d"
          % (len(rows), stats["eligible"], stats["frozen"], total))
    print("classes: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["classes"].items()))
    print("%d record(s) carry a hold on file; %d carry an overlapping series"
          % (stats["holds_on_file"], stats["overlap_on_file"]))
    print("%d (%.0f%%) carry an officer note whose TONE contradicts the verdict"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d record(s) are frozen AND already queued for destruction -- the review flag"
          % stats["needs_review"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every verdict is that document's own derivation, every class produced the verdict it "
          "was named for)")


if __name__ == "__main__":
    main()
