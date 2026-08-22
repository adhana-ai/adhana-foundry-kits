#!/usr/bin/env python3
"""Generate synthetic rights-and-option register snapshots and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one register snapshot per file) and data/gold.jsonl, byte-identical on
every run. Every property title, company, party, register identifier, payment reference and clerk
note here is INVENTED. No real work, studio, streaming service, publisher, guild, union, agency,
label, trade body, court, docket or person is named anywhere in this kit. Nothing is fetched and
nothing is licensed from anybody, so the corpus ships under this repo's MIT licence.

⚠︎ NO OPTION AGREEMENT, STANDARD FORM, RIGHTS-MANAGEMENT SYSTEM OR SCHEDULE IS REPRODUCED. The
rulebook this corpus is built against is `data/rulebook.json`, which was written for this kit and is
illustrative rather than authoritative. See data/SOURCES.md.

⚑ A MONITORING SNAPSHOT IS THE DOCUMENT, AND THAT IS THE WHOLE SHAPE OF A MONITOR KIT. Each file is
one property's rights register as it stood on one day: the obligations that apply to it, what has
actually happened so far, and what somebody last typed in the status column. Nothing here polls,
schedules, subscribes or watches. The kit reads one snapshot and proposes a worklist.

⚑ GOLD `status` IS A COUNT, NOT A LABEL SOMEBODY TYPED. It is derived from the same values the
generator itself decided, with the same rule the kit publishes everywhere else --
src/rulebook.py::decide(), which src/prompt.py states to the model in words and evals/judge.py
re-runs over the model's own reply to produce the published answer. It is never derived from the
register's own status line and never from the clerk's note.

⚑ THE FOUR STEPS OF THE COUNT, AND WHY THEY HAVE AN ORDER. What starts the clock; which extensions
were actually perfected; add the months consecutively from the clock start; compare against the
as-of date and the window. Each planted bucket below exists because a reader who skips one of those
steps, or takes them out of order, gets that bucket wrong:

  ext_no_payment          -- an extension the register RECORDS as exercised, controlled by payment,
                             with no payment recorded. It does not stack. Count it and the option
                             reads `live`; refuse to count it and the option is lapsed or lapsing.
                             Asserted at build time, not hoped for.
  ext_wrong_party         -- a notice-controlled extension whose notice went to the agent, the
                             co-financier, the escrow party or the grantee's own counsel rather
                             than to the grantor of record. Same consequence, and it looks more
                             correct than the payment case, not less.
  trigger_not_occurred    -- the clock runs from a triggering event that has not happened. There is
                             nothing to count from, so the answer is `not_determinable`. Reading it
                             as `live` removes a row from the worklist and looks like good news.
  grant_date_conflict     -- two entries on the same register disagree about the grant date, and
                             the clock runs from the grant date. The start is not settled.
  conflict_but_immaterial -- the SAME two disagreeing entries, on a register whose clock runs from
                             a triggering event that HAS occurred. The grant date is not an input,
                             so the disagreement changes nothing and the option is genuinely live.
                             ⚑ THIS IS THE CORPUS'S OWN FALSE-ALARM TRAP: a reader who flags every
                             contradiction cries wolf here, and on a monitoring queue a false alarm
                             costs a person exactly what a real one costs.
  lapsed_carried_live     -- expired, and the register still carries it as live.
  carried_lapsed_but_live -- the mirror: the register carries `lapsed`, and a properly perfected
                             extension means the option is in fact live. The register's error in
                             the OTHER direction, and the source of the free floor's false alarms.

⚑ THE PLANTED AMBIGUITY: the status is a count, and the rights clerk's own note disagrees with it
on `N_AMBIGUOUS` of registers. A file that has already lapsed carries "Nothing outstanding on this
one."; a file with two years to run carries "This one looks tight to me -- worth a second pair of
eyes." Anything that classifies off the note's TONE -- including evals/baseline.py, deliberately --
fails those registers by construction. Anything that counts gets them right.
"""
import argparse
import datetime
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import rulebook as RB                      # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 50

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the fix a sibling kit in
# this series had to make after its first generator asked for 40 pct ambiguity and delivered 51. A
# count 1.7 standard deviations off its own design is not a corpus property, it is sampling noise
# being published as one. So every bucket here is a fixed COUNT, shuffled by the seeded RNG.
#
# ⚠︎ AND THE MAJORITY OF THIS CORPUS IS ORDINARY ON PURPOSE. 18 of the 50 registers say exactly
# what they mean and the register's own status line agrees with the count. A corpus where the file
# is wrong most of the time is a corpus built to flatter the model -- the interesting claim is that
# the count finds the MINORITY the register gets wrong, without crying wolf over the majority it
# gets right.
BUCKETS = [
    ("live_clear", 10),               # ordinary, well beyond the window, register agrees
    ("lapsed_plain", 8),              # ordinary, expired, register agrees
    ("carried_lapsed_but_live", 4),   # register says lapsed; a perfected extension says otherwise
    ("conflict_but_immaterial", 3),   # two grant dates, and the clock does not run from either
    ("lapsing_window", 4),            # expires inside the window; the register has no word for it
    ("lapsed_carried_live", 3),       # expired and still carried as live
    ("ext_no_payment", 5),            # recorded exercised, payment-controlled, nothing paid
    ("ext_wrong_party", 4),           # notice-controlled, served on the wrong party
    ("trigger_not_occurred", 5),      # the clock has not started
    ("grant_date_conflict", 4),       # two grant dates, and the clock runs from the grant date
]
N_AMBIGUOUS = 20                      # 40 pct, exactly -- a clerk note from the wrong register
N_CLAMP_WANTED = 12                   # registers asked to land on the short-month clause

# Every register snapshot is current as at one of these days. Varied, so `register_as_of` has to be
# READ rather than assumed -- a monitor kit whose "today" is a constant is measuring nothing about
# whether the model found the snapshot's own moment.
AS_OF_DATES = ["2026-08-10", "2026-08-14", "2026-08-17", "2026-08-20", "2026-08-22"]

# Invented property titles. Nothing here is a real work, and no title, character, franchise or
# rights-holding organisation below exists.
TITLES = [
    "The Salt Harvest", "Ninth of Winter", "Lantern Street", "A Quiet Inventory",
    "The Kettleman Papers", "Marrow and Ash", "Undercurrent", "The Tin Orchard",
    "Every Second House", "The Coldwater Letters", "Halfway to Ostend", "The Paper Season",
    "Braid of Rivers", "The Long Commission", "Sixpenny Field", "A Borrowed Country",
    "The Glasshouse Year", "Thirteen Windows", "The Quarry Road", "Small Hours, Loud Streets",
    "The Fenmarket Case", "Anvil Bay", "The Ledger of Storms", "Nobody's Weather",
    "The Ropewalk", "Two Rivers Deep", "The Understudy's War", "Clay and Copper",
    "The Wintering Ground", "Aftermath of Larks",
]
TITLE_KINDS = ["unpublished novel", "stage play", "short-story collection", "graphic novel",
               "non-fiction narrative", "radio serial", "novella", "essay collection"]

# Invented grantors (rights holders) and grantees. No real publisher, studio, streamer, label,
# agency, guild or production company is named.
RIGHTS_HOLDERS = [
    "Marrowfield Editions Limited", "Quillhaven Press Limited", "Beckridge Literary Trust",
    "Ostend Row Publishing Limited", "Fenmarket Books Limited", "The Copperline Estate",
    "Ashlyn Grove Publishing Limited", "Saltcote Editions Limited",
]
GRANTEES = [
    "Ninebark Pictures LLC", "Harrowgate Screen Limited", "Sundermere Productions Limited",
    "Bright Quarry Media LLC", "Peregrine Lane Films Limited", "Ashwater Content Group LLC",
    "Larkhill Screen Partners LLC", "Foxbourne Pictures Limited",
]
# Parties who are NOT the grantor of record. Serving notice on any of them does not perfect a
# notice-controlled extension, however customary the practice is.
WRONG_PARTIES = [
    ("%s (the grantor's literary agent)", "agent"),
    ("%s (co-financier of record)", "co-financier"),
    ("%s (escrow agent)", "escrow"),
    ("%s (the grantee's own counsel)", "counsel"),
]
AGENTS = ["Halloway Rights Agency", "Pentland & Voss Literary", "The Ivory Row Agency",
          "Camberford Rights Partners", "Netherby Literary Management"]
COUNSEL = ["Drummond Vale LLP", "Ashbourne Craig LLP", "Whitfield Roe LLP"]
ESCROW = ["Sarnfield Escrow Services Limited", "Beaufort Clearing Limited"]
COFIN = ["Tidewell Capital Partners LLC", "Braemore Content Finance LLC"]

TRIGGER_EVENTS = [
    "delivery of the completed manuscript to the grantee",
    "clearance of the underlying life-story consents",
    "the grantee's written notice that principal financing has closed",
    "publication of the trade edition",
    "expiry of the prior option held by a third party",
]

# Notes whose TONE says "this file is fine". Used truthfully on a register whose counted status is
# `live`, and against type on one that is not -- half the planted ambiguity.
CALM_NOTES = [
    "Nothing outstanding on this one. Paperwork all looks in order to me.",
    "Routine file. No queries from either side since the last review.",
    "Comfortable with where this sits. Happy to leave it until the next sweep.",
    "Clean file, nothing for the desk to do here as far as I can see.",
]
# Notes whose TONE says "something needs looking at". Used truthfully on a register whose counted
# status is not `live`, and against type on one that is fine -- the other half.
WORRIED_NOTES = [
    "This one looks tight to me -- worth a second pair of eyes before the next sweep.",
    "Chased the file twice and I am not confident the dates on it are settled.",
    "Something is off in the sequence here; flagged for review by the rights desk.",
    "Escalated internally last week; nobody has come back on the paperwork yet.",
]

TERMS = (12, 18, 24)
EXT_LENGTHS = (6, 12)
PAY_REFS = "PMT"


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------

def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs. Deterministic."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    while len(out) < n:
        out.append(spec[0][0])
    out = out[:n]
    rng.shuffle(out)
    return out


def _d(iso):
    return datetime.date.fromisoformat(iso)


def _band_of(as_of_iso, expiry_iso):
    """Which of the three dated statuses an expiry falls in, for this as-of date."""
    days = (_d(expiry_iso) - _d(as_of_iso)).days
    if days <= 0:
        return "lapsed"
    if days <= RB.WINDOW_DAYS:
        return "lapsing"
    return "live"


def _pick_start_for_band(rng, as_of, total_months, band, clamp=False):
    """A clock-start date whose expiry lands in `band`. Forward construction: pick a start, add the
    months, check the band, retry.

    ⚠︎ FORWARD ON PURPOSE, RATHER THAN SUBTRACTING MONTHS FROM A TARGET EXPIRY. Subtracting is not
    the inverse of adding when a month is short, so a corpus built backwards would quietly never
    produce a clamped expiry -- and the clamping clause would be a rule this kit states and never
    exercises.

    ⚑ `clamp` ASKS FOR A START WHOSE DAY-OF-MONTH CANNOT SURVIVE THE ADDITION -- a 29th, 30th or
    31st landing in a shorter month. The rulebook has a clause about it, and a stated clause no row
    exercises is a rule this corpus cannot measure. The request is a PREFERENCE, not a demand: it
    falls back to any start in the band rather than failing, and `_verify` counts how many rows
    actually landed on it so the published number is the real one.
    """
    a = _d(as_of)
    nominal = int(round(total_months * 30.44))
    lo, hi = max(1, nominal - 520), nominal + 380
    # A start somewhere either side of "one term ago", so all three bands are reachable for every
    # term length. `lapsing` is the narrow one -- 45 days of a ~900-day range -- which is why the
    # loop is generous rather than clever.
    fallback = None
    for i in range(12000):
        start = a - datetime.timedelta(days=rng.randint(lo, hi))
        end = RB.add_months(start, total_months)
        if not end or _band_of(as_of, end.isoformat()) != band:
            continue
        if not clamp:
            return start.isoformat()
        if end.day != start.day:
            return start.isoformat()
        if fallback is None:
            fallback = start.isoformat()
    if fallback is not None:
        return fallback
    raise RuntimeError("no clock start lands in band %r for %d months at %s"
                       % (band, total_months, as_of))


def _wrong_party(rng, rights_holder):
    kind = rng.choice(WRONG_PARTIES)
    pool = {"agent": AGENTS, "counsel": COUNSEL, "escrow": ESCROW, "co-financier": COFIN}[kind[1]]
    return kind[0] % rng.choice(pool)


# --------------------------------------------------------------------------------------------
# One constructor per bucket. Each returns a dict of the values the register will state, and each
# is ASSERTED against the rulebook at the end of build_all -- a constructor that quietly stops
# producing its own bucket is exactly the defect an exact composition exists to prevent.
#
# Shared shape returned by every constructor:
#   as_of, granted, granted_second (or None), basis, trig_status, trig_event, trig_date,
#   initial, ext_len, exts (a list of extension dicts), register_status
# An extension dict is {controls, recorded, exercised_on, pay_ref, pay_date, notice_party,
#                       perfected}.
# --------------------------------------------------------------------------------------------

def _ext(controls, recorded, exercised_on=None, pay_ref=None, pay_date=None, notice_party=None,
         perfected=False):
    return {"controls": controls, "recorded": recorded, "exercised_on": exercised_on,
            "pay_ref": pay_ref, "pay_date": pay_date, "notice_party": notice_party,
            "perfected": perfected}


def _pay_ref(rng):
    return "%s-%05d" % (PAY_REFS, rng.randint(10000, 99999))


def _good_ext(rng, controls, start_iso, months_in, rights_holder):
    """A properly perfected extension: exercised, and the act the agreement names actually done."""
    ex = _d(start_iso) + datetime.timedelta(days=rng.randint(20, months_in * 28))
    if controls == "payment":
        return _ext("payment", "exercised", ex.isoformat(), _pay_ref(rng),
                    (ex - datetime.timedelta(days=rng.randint(0, 6))).isoformat(),
                    rights_holder, perfected=True)
    return _ext("notice", "exercised", ex.isoformat(), None, None, rights_holder, perfected=True)


def _untaken_ext(controls):
    return _ext(controls, "not exercised")


def _basis(rng, force=None):
    """A clock basis, with a triggering event that HAS occurred on about a third of registers.

    ⚑ A TRIGGERING EVENT IS NOT A GIVEAWAY FOR `not_determinable`, AND THAT IS DELIBERATE. If the
    only registers with a triggering-event clock were the ones whose event had not happened, a
    model could answer the whole bucket off the word `triggering_event` and never read the line
    that matters.
    """
    if force:
        return force
    return "triggering_event" if rng.random() < 0.34 else "grant_date"


def _make(rng, bucket, clamp=False):
    as_of = rng.choice(AS_OF_DATES)
    rights_holder = rng.choice(RIGHTS_HOLDERS)
    initial = rng.choice(TERMS)
    ext_len = rng.choice(EXT_LENGTHS)
    n_avail = rng.choice((1, 2))
    granted_second = None
    trig_event = None
    trig_date = None
    trig_status = "not_applicable"

    # ---- the two contradiction buckets ------------------------------------------------------
    if bucket == "grant_date_conflict":
        basis = "grant_date"
        exts = [_untaken_ext(rng.choice(("payment", "notice"))) for _ in range(n_avail)]
        granted = (_d(as_of) - datetime.timedelta(days=rng.randint(200, 900))).isoformat()
        granted_second = (_d(granted)
                          + datetime.timedelta(days=rng.choice((11, 14, 19, 23, 31)))).isoformat()
        return dict(as_of=as_of, rights_holder=rights_holder, granted=granted,
                    granted_second=granted_second, basis=basis, trig_status=trig_status,
                    trig_event=trig_event, trig_date=trig_date, initial=initial, ext_len=ext_len,
                    exts=exts, register_status="live")

    if bucket == "conflict_but_immaterial":
        basis = "triggering_event"
        trig_status = "occurred"
        trig_event = rng.choice(TRIGGER_EVENTS)
        n_perf = rng.choice((0, 1)) if n_avail >= 1 else 0
        total = initial + ext_len * n_perf
        trig_date = _pick_start_for_band(rng, as_of, total, "live", clamp=clamp)
        exts = []
        for i in range(n_avail):
            controls = rng.choice(("payment", "notice"))
            if i < n_perf:
                exts.append(_good_ext(rng, controls, trig_date, initial, rights_holder))
            else:
                exts.append(_untaken_ext(controls))
        granted = (_d(trig_date) - datetime.timedelta(days=rng.randint(60, 400))).isoformat()
        granted_second = (_d(granted)
                          + datetime.timedelta(days=rng.choice((9, 16, 21, 28)))).isoformat()
        return dict(as_of=as_of, rights_holder=rights_holder, granted=granted,
                    granted_second=granted_second, basis=basis, trig_status=trig_status,
                    trig_event=trig_event, trig_date=trig_date, initial=initial, ext_len=ext_len,
                    exts=exts, register_status="live")

    if bucket == "trigger_not_occurred":
        basis = "triggering_event"
        trig_status = "not_occurred"
        trig_event = rng.choice(TRIGGER_EVENTS)
        granted = (_d(as_of) - datetime.timedelta(days=rng.randint(150, 800))).isoformat()
        exts = [_untaken_ext(rng.choice(("payment", "notice"))) for _ in range(n_avail)]
        return dict(as_of=as_of, rights_holder=rights_holder, granted=granted,
                    granted_second=None, basis=basis, trig_status=trig_status,
                    trig_event=trig_event, trig_date=None, initial=initial, ext_len=ext_len,
                    exts=exts, register_status="live")

    # ---- the two unperfected-extension buckets ----------------------------------------------
    if bucket in ("ext_no_payment", "ext_wrong_party"):
        controls = "payment" if bucket == "ext_no_payment" else "notice"
        basis = _basis(rng)
        n_avail = max(n_avail, 1)
        band = rng.choice(("lapsed", "lapsing"))
        # The option WITHOUT the unperfected extension lands in `band`; WITH it counted it must
        # read `live`. Both halves are asserted below in `_verify`, not hoped for.
        for _ in range(3000):
            start = _pick_start_for_band(rng, as_of, initial, band, clamp=clamp)
            with_ext = RB.add_months(_d(start), initial + ext_len)
            if with_ext and _band_of(as_of, with_ext.isoformat()) == "live":
                break
        else:
            raise RuntimeError("%s: no start where the extension flips the band" % bucket)
        ex = _d(start) + datetime.timedelta(days=rng.randint(30, initial * 28))
        if controls == "payment":
            bad = _ext("payment", "exercised", ex.isoformat(), None, None, rights_holder,
                       perfected=False)
        else:
            bad = _ext("notice", "exercised", ex.isoformat(), None, None,
                       _wrong_party(rng, rights_holder), perfected=False)
        exts = [bad] + [_untaken_ext(rng.choice(("payment", "notice")))
                        for _ in range(n_avail - 1)]
        if basis == "triggering_event":
            trig_status, trig_event, trig_date = "occurred", rng.choice(TRIGGER_EVENTS), start
            granted = (_d(start) - datetime.timedelta(days=rng.randint(45, 300))).isoformat()
        else:
            granted = start
        return dict(as_of=as_of, rights_holder=rights_holder, granted=granted,
                    granted_second=None, basis=basis, trig_status=trig_status,
                    trig_event=trig_event, trig_date=trig_date, initial=initial, ext_len=ext_len,
                    exts=exts, register_status="live")

    # ---- the four plain-band buckets --------------------------------------------------------
    band = {"live_clear": "live", "lapsed_plain": "lapsed", "lapsing_window": "lapsing",
            "lapsed_carried_live": "lapsed", "carried_lapsed_but_live": "live"}[bucket]
    register_status = {"live_clear": "live", "lapsed_plain": "lapsed",
                       "lapsing_window": "live", "lapsed_carried_live": "live",
                       "carried_lapsed_but_live": "lapsed"}[bucket]
    basis = _basis(rng)
    # carried_lapsed_but_live turns on a properly PERFECTED extension, so it always has one.
    n_perf = 1 if bucket == "carried_lapsed_but_live" else rng.choice((0, 0, 1))
    n_avail = max(n_avail, n_perf)
    total = initial + ext_len * n_perf
    start = _pick_start_for_band(rng, as_of, total, band, clamp=clamp)
    exts = []
    for i in range(n_avail):
        controls = rng.choice(("payment", "notice"))
        if i < n_perf:
            exts.append(_good_ext(rng, controls, start, initial, rights_holder))
        else:
            exts.append(_untaken_ext(controls))
    if basis == "triggering_event":
        trig_status, trig_event, trig_date = "occurred", rng.choice(TRIGGER_EVENTS), start
        granted = (_d(start) - datetime.timedelta(days=rng.randint(45, 300))).isoformat()
    else:
        granted = start
    return dict(as_of=as_of, rights_holder=rights_holder, granted=granted, granted_second=None,
                basis=basis, trig_status=trig_status, trig_event=trig_event, trig_date=trig_date,
                initial=initial, ext_len=ext_len, exts=exts, register_status=register_status)


EXPECTED_STATUS = {
    "live_clear": "live",
    "lapsed_plain": "lapsed",
    "carried_lapsed_but_live": "live",
    "conflict_but_immaterial": "live",
    "lapsing_window": "lapsing",
    "lapsed_carried_live": "lapsed",
    "ext_no_payment": ("lapsed", "lapsing"),
    "ext_wrong_party": ("lapsed", "lapsing"),
    "trigger_not_occurred": "not_determinable",
    "grant_date_conflict": "not_determinable",
}


def _render_extension(label, e):
    lines = [_underline(label)]
    lines.append("%%d months, perfected by %s" % e["controls"])
    if e["recorded"] == "exercised":
        lines.append("recorded: exercised %s" % e["exercised_on"])
        if e["controls"] == "payment":
            if e["pay_ref"]:
                lines.append("payment: %s dated %s" % (e["pay_ref"], e["pay_date"]))
            else:
                lines.append("payment: none recorded against this extension")
        else:
            lines.append("notice served on: %s" % e["notice_party"])
    else:
        lines.append("recorded: not exercised")
    return lines


def build_all(rng, n=N_RECORDS):
    spec = list(BUCKETS)
    if n != N_RECORDS:                       # a --n other than the design keeps the shape, roughly
        spec = [(name, max(1, round(count * n / N_RECORDS))) for name, count in BUCKETS]
    buckets = _deal(rng, n, spec)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    # ⚑ ASKED FOR, NOT HOPED FOR. Without this the short-month clause in the
    # rulebook would be a rule stated on every page and exercised by no row.
    clamps = _deal(rng, n, [(True, N_CLAMP_WANTED), (False, n - N_CLAMP_WANTED)])
    titles = list(TITLES)
    rng.shuffle(titles)

    stats = {"statuses": {}, "buckets": {name: 0 for name, _ in BUCKETS}, "ambiguous": 0,
             "escalate": 0, "clamped": 0, "register_disagrees": 0, "recorded_not_perfected": 0,
             "trigger_basis": 0}

    out = []
    for i in range(1, n + 1):
        bucket = buckets[i - 1]
        v = _make(rng, bucket, clamp=clamps[i - 1])

        n_recorded = sum(1 for e in v["exts"] if e["recorded"] == "exercised")
        n_perfected = sum(1 for e in v["exts"] if e["perfected"])

        # ⚑ THE GRANT DATE THE MODEL MUST REFUSE TO SETTLE. Two entries, both plausible, from two
        # plausible sources, and the rulebook explicitly forbids breaking the tie. `gold_granted`
        # is therefore None on both contradiction buckets, and it is what the count is run over --
        # feeding the count the FIRST of the two entries would build gold from a tie-break the
        # rulebook forbids, which is the one way a generated corpus can lie about its own rule.
        if v["granted_second"] is not None:
            granted_lines = [
                "%s (option agreement, executed copy)" % v["granted"],
                "%s (rights schedule, same grant, same parties)" % v["granted_second"],
            ]
            gold_granted = None
        else:
            granted_lines = ["%s (option agreement, executed copy)" % v["granted"]]
            gold_granted = v["granted"]

        d = RB.decide(v["as_of"], v["basis"], v["trig_status"], gold_granted, v["trig_date"],
                      v["initial"], v["ext_len"], n_perfected)
        status = d["status"]
        want = EXPECTED_STATUS[bucket]
        want = (want,) if isinstance(want, str) else want
        assert status in want, "%s produced %r, not one of %r" % (bucket, status, want)

        rec_id = "ROR-%04d" % i
        register_id = "RGT-%04d-%s%s" % (rng.randint(1000, 9999),
                                         rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                         rng.choice("ABCDEFGHJKLMNPRSTVW"))
        title = titles[(i - 1) % len(titles)]
        kind = rng.choice(TITLE_KINDS)
        grantee = rng.choice(GRANTEES)

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        calm = (status == "live") if not ambiguous else (status != "live")
        note = rng.choice(CALM_NOTES if calm else WORRIED_NOTES)
        note_register = "calm" if calm else "worried"

        if v["basis"] == "grant_date":
            basis_line = "grant_date -- the option period runs from the date the option was granted"
            trigger_lines = ["not applicable -- this option carries no triggering event"]
        else:
            basis_line = ("triggering_event -- the option period runs from %s" % v["trig_event"])
            if v["trig_status"] == "occurred":
                trigger_lines = ["%s" % v["trig_event"],
                                 "occurred: %s" % v["trig_date"]]
            else:
                trigger_lines = ["%s" % v["trig_event"],
                                 "occurred: not yet, as at the date of this register"]

        filing = [
            "file opened %s by the rights desk"
            % (_d(v["as_of"]) - datetime.timedelta(days=rng.randint(400, 1400))).isoformat(),
            "last reindexed %s"
            % (_d(v["as_of"]) - datetime.timedelta(days=rng.randint(5, 60))).isoformat(),
            "file class: %s, single-property register" % rng.choice(
                ("dramatic rights", "audio-visual rights", "adaptation rights")),
        ]

        lines = [
            _underline("Register"), register_id, "",
            _underline("Property"), '"%s" -- %s' % (title, kind), "",
            _underline("Rights Holder"), v["rights_holder"], "",
            _underline("Grantee"), grantee, "",
            _underline("Register As Of"), v["as_of"], "",
            _underline("Option Granted")] + granted_lines + ["",
            _underline("Clock Basis"), basis_line, "",
            _underline("Triggering Event")] + trigger_lines + ["",
            _underline("Initial Option Period"), "%d months" % v["initial"], "",
        ]
        labels = ["Extension One", "Extension Two", "Extension Three"]
        for j, e in enumerate(v["exts"]):
            block = _render_extension(labels[j], e)
            block[1] = block[1] % v["ext_len"]
            lines += block + [""]
        lines += [
            _underline("Filing History")] + filing + ["",
            _underline("Register Status"), v["register_status"], "",
            _underline("Clerk Note"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "register_ref": rec_id,
            "register_id": register_id,
            "property_title": title,
            "rights_holder": v["rights_holder"],
            "grantee": grantee,
            "register_as_of": v["as_of"],
            "option_granted_date": gold_granted,
            "clock_basis": v["basis"],
            "trigger_status": v["trig_status"],
            "trigger_date": v["trig_date"],
            "initial_term_months": v["initial"],
            "extension_months_each": v["ext_len"],
            "extensions_recorded_taken": n_recorded,
            "extensions_perfected": n_perfected,
            "register_status": v["register_status"],
            "clerk_note": note,
            "expiry_date": d["expiry_date"],
            "status": status,
            # Not a scored field -- a label on the PLANTED note register, so evals/judge.py can
            # report accuracy on the rows whose clerk note points the wrong way without the
            # judge having to import the generator's own note lists.
            "note_register": note_register,
        }
        out.append((rec_id, text, gold, bucket))

        stats["statuses"][status] = stats["statuses"].get(status, 0) + 1
        stats["buckets"][bucket] += 1
        if status != "live" and v["register_status"] == "live":
            stats["escalate"] += 1
        if (v["register_status"] == "live") != (status == "live"):
            stats["register_disagrees"] += 1
        if n_recorded > n_perfected:
            stats["recorded_not_perfected"] += 1
        if v["basis"] == "triggering_event":
            stats["trigger_basis"] += 1
        # A clamped expiry: the start day-of-month could not be preserved.
        if d["expiry_date"] and d["clock_start_date"]:
            if _d(d["expiry_date"]).day != _d(d["clock_start_date"]).day:
                stats["clamped"] += 1
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the register it labels, every gold status must be that
    register's own rulebook count, and each nullable field must be null exactly when the register
    says so. A corpus whose labels are not readable off its own text is not a corpus, it is a
    second opinion."""
    for rec_id, text, gold, bucket in rows:
        for field in ("register_id", "property_title", "rights_holder", "grantee",
                      "register_as_of", "clerk_note"):
            assert gold[field] in text, "%s: %s not stated in the register" % (rec_id, field)
        assert "%d months" % gold["initial_term_months"] in text, \
            "%s: initial term not stated" % rec_id
        assert "%d months, perfected by" % gold["extension_months_each"] in text, \
            "%s: extension length not stated" % rec_id

        if gold["option_granted_date"] is None:
            assert "rights schedule, same grant" in text, \
                "%s: null grant date is not explained by two disagreeing entries" % rec_id
        else:
            assert gold["option_granted_date"] in text, "%s: grant date not stated" % rec_id

        if gold["trigger_date"] is None:
            assert ("not applicable" in text or "occurred: not yet" in text), \
                "%s: null trigger date not explained" % rec_id
        else:
            assert "occurred: %s" % gold["trigger_date"] in text, \
                "%s: trigger date not stated verbatim" % rec_id

        want = RB.decide(gold["register_as_of"], gold["clock_basis"], gold["trigger_status"],
                         gold["option_granted_date"], gold["trigger_date"],
                         gold["initial_term_months"], gold["extension_months_each"],
                         gold["extensions_perfected"])
        assert gold["status"] == want["status"], \
            "%s: gold status %r disagrees with its own rulebook count (%r)" \
            % (rec_id, gold["status"], want["status"])
        assert gold["expiry_date"] == want["expiry_date"], \
            "%s: gold expiry %r disagrees with its own count (%r)" \
            % (rec_id, gold["expiry_date"], want["expiry_date"])
        assert (gold["expiry_date"] is None) == (gold["status"] == "not_determinable"), \
            "%s: a null expiry and a not_determinable status must be the same rows" % rec_id

        # ⚑ THE POINT OF THE TWO EXTENSION BUCKETS, ASSERTED HERE RATHER THAN HOPED FOR: counting
        # the extension the register RECORDS as taken makes the option read `live`. Everything that
        # makes it a worklist row is one act the register did not actually get done.
        if bucket in ("ext_no_payment", "ext_wrong_party"):
            assert gold["extensions_recorded_taken"] > gold["extensions_perfected"], \
                "%s: %s must record an extension it did not perfect" % (rec_id, bucket)
            counted = RB.decide(gold["register_as_of"], gold["clock_basis"],
                                gold["trigger_status"], gold["option_granted_date"],
                                gold["trigger_date"], gold["initial_term_months"],
                                gold["extension_months_each"],
                                gold["extensions_recorded_taken"])
            assert counted["status"] == "live", \
                "%s: counting the unperfected extension must read as live, got %r" \
                % (rec_id, counted["status"])
            assert gold["status"] in ("lapsed", "lapsing"), \
                "%s: refusing to count it must produce a worklist row, got %r" \
                % (rec_id, gold["status"])

        # ⚑ AND THE FALSE-ALARM TRAP, ASSERTED THE SAME WAY: a reader who treats every grant-date
        # contradiction as fatal answers not_determinable here, and the true answer is `live`.
        if bucket == "conflict_but_immaterial":
            assert gold["option_granted_date"] is None, \
                "%s: conflict_but_immaterial must carry two disagreeing grant dates" % rec_id
            assert gold["clock_basis"] == "triggering_event" \
                and gold["trigger_status"] == "occurred", \
                "%s: the conflict is only immaterial when the clock runs elsewhere" % rec_id
            assert gold["status"] == "live", \
                "%s: conflict_but_immaterial must count to live, got %r" \
                % (rec_id, gold["status"])


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
    for rec_id, text, _gold, _bucket in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold, _bucket in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    total = sum(len(t.encode("utf-8")) for _i, t, _g, _b in rows)
    print("registers: %d   bytes: %d" % (len(rows), total))
    print("statuses: %s" % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["statuses"].items())))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["buckets"].items()))
    print("%d (%.0f%%) carry a clerk note whose TONE contradicts the counted status"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d register(s) record an extension as exercised that was never perfected"
          % stats["recorded_not_perfected"])
    print("%d register(s) run their clock from a triggering event" % stats["trigger_basis"])
    print("%d register(s) have a status line that disagrees with the count (live vs not-live)"
          % stats["register_disagrees"])
    print("%d register(s) are not live AND still carried as live -- the pure-code escalation flag"
          % stats["escalate"])
    print("%d expiry date(s) land on a clamped day-of-month (the short-month clause, exercised)"
          % stats["clamped"])
    print("internal consistency check: PASSED (every gold value is stated in its own register, "
          "every status is that register's own rulebook count, every nullable field is explained "
          "in the text, and both flip-the-band properties are asserted)")


if __name__ == "__main__":
    main()
