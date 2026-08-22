#!/usr/bin/env python3
"""Generate synthetic label-restriction cases and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one case per file) and data/gold.jsonl, byte-identical on every run.
Every product name, registration number, active substance, field identifier and agronomist note
here is INVENTED; every crop name is an ordinary generic crop noun. Nothing is fetched and nothing
is licensed from anybody, so the corpus ships under this repo's MIT licence.

⚠︎ NO REAL PRODUCT, MANUFACTURER, ACTIVE SUBSTANCE, REGISTRATION OR REGULATOR IS NAMED OR
REPRODUCED. The check set this corpus is built against is `data/checks.json`, which was written for
this kit and is illustrative rather than authoritative. See data/SOURCES.md.

⚑ GOLD IS A WALK OF THE CHECK SET, NOT A LABEL SOMEBODY TYPED. Both `verdict` AND
`deciding_restriction` are derived from the same twenty structured values the generator itself
decided, with the same rule the kit publishes everywhere else -- src/checks.py::decide(), which
src/prompt.py renders to the model out of the same JSON file and evals/judge.py re-runs over the
model's own reply. Neither is ever derived from the agronomist's note, and the note never feeds a
label.

⚑ TWO ANSWERS PER CASE, SCORED SEPARATELY, AND THE SECOND IS THE POINT OF THIS KIT. A verdict of
`wait_required` that names the pre-harvest interval when the case actually turns on the re-entry
interval is a right answer for the wrong reason -- and a grower told to wait the wrong number of
the wrong unit from the wrong date has not been helped. This corpus is built so that failure mode
is REACHABLE and MEASURABLE rather than hypothetical: fourteen cases turn on one of three
confusable intervals, four of them on the one interval measured in hours.

⚑ THE HARD BUCKETS, AND WHY EACH EXISTS. Every one is a reading a careful person still gets wrong:

  season_max_reached  -- `maximum applications per season: 3` with `applications already made this
                         season: 3`. It reads as "at the limit, therefore inside" and it is the
                         opposite: the limit is a total and this proposal is the next one. On some
                         of these the RATE also sits exactly on its maximum, which IS inside --
                         so the two inclusive-vs-exclusive readings sit on the same page.
  crop_not_permitted  -- the permitted list carries a NEAR NEIGHBOUR of the proposed crop: winter
                         wheat beside spring wheat, field lettuce beside protected lettuce. A
                         reader matching on the head noun clears an application the label does not.
  rei_short           -- the re-entry interval is the only restriction on the label in HOURS, and
                         its numbers sit in the same range as the day counts above it. A reader
                         comparing 48 against a 48-day harvest window satisfies it by accident.
  hard_and_timing     -- a hard restriction AND a timing one are both breached. The answer is
                         `outside_label`; a reader who stops at the first date they recognise says
                         `wait_required`, which tells a grower to wait for an application that must
                         not be made at all. The most expensive wrong answer this kit can give.
  label_silent        -- the label extract does not state the interval this proposal turns on.
                         That is `insufficient_information`, naming the restriction -- not a pass,
                         and not a guess.
  proposal_silent     -- the proposal does not state days to harvest. Same answer, other side of
                         the page.
  within_at_limit     -- every value sits EXACTLY on its limit and every limit is inclusive, so
                         the whole case is inside the label. It looks like six breaches and is none.

⚑ THE PLANTED AMBIGUITY: the verdict is a walk of the check set, and the agronomist's own note
disagrees with it on `N_AMBIGUOUS` of cases. A proposal that must not be made carries a relaxed
note ("Routine programme for this block. Nothing about it concerns me."); one that is entirely
inside the label carries a note that reads as though something is wrong with it. Anything that
classifies off the note's TONE -- including evals/baseline.py, deliberately -- fails those cases by
construction. Anything that walks the check set gets them right.

⚑ AND A SECOND DECOY THAT IS NOT ABOUT TONE AT ALL. Every case states how many applications were
made in the PREVIOUS season. The label maximum is per season, so that number is part of no check.
On every one of the `within_label` cases it is set so that ADDING it to this season's count would
cross the maximum -- a reader who adds them refuses an application that is inside the label.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import checks as CK                       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 52

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the fix a sibling kit in
# this series had to make after its first generator asked for 40 pct ambiguity and delivered 51.
# A count 1.7 standard deviations off its own design is not a corpus property, it is sampling
# noise being published as one. So every bucket here is a fixed COUNT, shuffled by the seeded RNG.
BUCKETS = [
    ("within_ordinary", 8),          # inside the label with room to spare
    ("within_at_limit", 6),          # every value exactly on its limit -- and every limit is inclusive
    ("crop_not_permitted", 4),       # a near neighbour of a permitted crop
    ("rate_over_max", 3),            # one rung above the maximum rate
    ("season_max_reached", 4),       # the off-by-one: the maximum is a total
    ("tank_mix_prohibited", 2),      # the partner is on the label's prohibited list
    ("buffer_too_small", 1),         # nearer the water than the label allows
    ("hard_and_timing", 4),          # a hard breach AND a timing one -- precedence decides
    ("retreatment_short", 5),        # not long enough since the last application
    ("phi_short", 5),                # harvest is nearer than the pre-harvest interval
    ("rei_short", 4),                # re-entry planned sooner than the interval -- in HOURS
    ("label_silent", 4),             # the label extract does not state the deciding interval
    ("proposal_silent", 2),          # the proposal does not state days to harvest
]
N_AMBIGUOUS = 21                     # 40.4 pct -- an agronomist note from the wrong register
N_APPLIED = 23                       # application_status == "applied"; the rest are "planned"

# Invented crops are not a thing -- these are ordinary generic crop nouns. The PAIRS are the point:
# each pair is two crops a careless reader treats as one.
CROP_PAIRS = [
    ("winter wheat", "spring wheat"),
    ("winter barley", "spring barley"),
    ("winter oilseed rape", "spring oilseed rape"),
    ("field lettuce", "protected lettuce"),
]
CROPS = [c for pair in CROP_PAIRS for c in pair] + [
    "maize", "sugar beet", "field beans", "potatoes", "carrots", "onions", "field peas",
]

# ⚠︎ EVERY PRODUCT NAME BELOW IS COINED FOR THIS KIT AND NAMES NO REAL PRODUCT. The near-name
# pairs are deliberate: on a real label a prohibited partner and a permitted one can differ by two
# syllables, and this corpus makes that reading testable rather than assumed.
PRODUCTS = [
    "Corvenal 250 SC", "Corvistel 275 SC",
    "Trelmara 400 EC", "Ondimara 150 EC",
    "Belquoris 100 WG", "Belquoran 120 WG",
    "Kestrival 480 SL", "Melbrasco 360 SL",
    "Ravelquin 300 SC", "Tarnwyth 200 WG",
    "Vantrisel 125 EC", "Hollowmere 450 SC",
]
# ⚠︎ COINED STRINGS, NOT CHEMISTRY. These name no real active substance and describe no real mode
# of action. They live only in the `Product and Registration` section, which src/select.py maps to
# no field and which is therefore never sent to the model at all -- see that module's note.
ACTIVES = ["korvamide", "delvestrin", "tresulan", "quinbaryl", "norsetane", "avomextil",
           "bractolin", "zemidral"]

# All non-integral, so a rate always prints and parses back the same way and a span never has to
# guess between "2" and "2.0".
RATES = [0.6, 0.75, 1.2, 1.25, 1.5, 1.8, 2.4, 2.5, 3.2, 3.5]
MAX_APPS = [1, 2, 3, 4]
RETREAT_DAYS = [7, 10, 14, 21, 28]
PHI_DAYS = [7, 14, 21, 28, 35, 42, 60]
REI_HOURS = [6, 12, 24, 48]
BUFFER_M = [1, 5, 6, 12, 18, 20]

# Notes whose TONE says "this application is fine". Used truthfully on a case whose verdict is
# `within_label`, and against type on one that is not -- half the planted ambiguity.
CALM_NOTES = [
    "Routine programme for this block. Nothing about it concerns me.",
    "Standard timing for the rotation here. I am happy for this one to go ahead.",
    "Straightforward application, nothing unusual about this parcel at all.",
    "This product has been used on this holding for years without incident.",
]
# Notes whose TONE says "something is wrong here". Used truthfully on a case whose verdict is not
# `within_label`, and against type on one that is entirely inside the label -- the other half.
WORRIED_NOTES = [
    "Not comfortable with this one -- asked the grower to hold off until it is checked.",
    "Something looked off against the label; flagged for a second read before spraying.",
    "Spray records for this parcel are disputed and are under manual audit this week.",
    "A watercourse here has been complained about before -- escalated to the agronomy lead.",
]


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


def _fmt(v):
    if isinstance(v, float) and abs(v - round(v)) < 1e-9:
        return "%d" % round(v)
    return ("%g" % v) if isinstance(v, float) else str(v)


def _up(ladder, v):
    """The next rung above `v`, or None when `v` is already the top."""
    i = ladder.index(v)
    return ladder[i + 1] if i + 1 < len(ladder) else None


def _base(rng):
    """A label and a proposal that satisfy every applicable check. Every bucket starts here and
    perturbs exactly one thing (or, for `hard_and_timing`, exactly two)."""
    pair = rng.choice(CROP_PAIRS)
    crop = pair[0]
    others = [c for c in CROPS if c not in pair]
    rng.shuffle(others)
    permitted = [crop] + others[:rng.randint(2, 4)]
    rng.shuffle(permitted)

    max_rate = rng.choice(RATES[2:])                 # leave room for a rung below it
    max_apps = rng.choice(MAX_APPS)
    retreat = rng.choice(RETREAT_DAYS)
    phi = rng.choice(PHI_DAYS)
    rei = rng.choice(REI_HOURS)
    buffer_m = rng.choice(BUFFER_M)

    prohibited_pool = [p for p in PRODUCTS]
    rng.shuffle(prohibited_pool)
    prohibited = prohibited_pool[:rng.choice([0, 1, 2, 2])]

    apps_made = rng.randint(0, max_apps - 1)
    rate = rng.choice([r for r in RATES if r <= max_rate])
    days_since = None if apps_made == 0 else retreat + rng.choice([0, 3, 7, 14])
    days_to_harvest = phi + rng.choice([0, 5, 12, 30])
    re_entry = rei + rng.choice([0, 6, 24])
    distance = buffer_m + rng.choice([0, 4, 10, 25])
    partner = "none" if rng.random() < 0.55 else rng.choice(
        [p for p in PRODUCTS if p not in prohibited])

    return {
        "permitted_crops": ", ".join(permitted),
        "max_rate_l_per_ha": max_rate,
        "max_applications_per_season": max_apps,
        "min_retreatment_interval_days": retreat,
        "pre_harvest_interval_days": phi,
        "re_entry_interval_hours": rei,
        "buffer_to_water_m": buffer_m,
        "tank_mix_prohibited_with": ", ".join(prohibited) if prohibited else "none",
        "crop_proposed": crop,
        "rate_proposed_l_per_ha": rate,
        "applications_made_this_season": apps_made,
        "days_since_last_application": days_since,
        "days_to_harvest": days_to_harvest,
        "planned_re_entry_hours": re_entry,
        "distance_to_water_m": distance,
        "tank_mix_partner": partner,
        "previous_season_applications": rng.randint(0, 3),
    }


# --------------------------------------------------------------------------------------------
# One constructor per bucket. Each returns the twenty structured values, and each is ASSERTED
# against the check set at the end of build_all -- a constructor that quietly stops producing its
# own bucket is exactly the defect an exact composition exists to prevent.
# --------------------------------------------------------------------------------------------

def _mk_within_ordinary(rng):
    v = _base(rng)
    return _decoy_previous(v)


def _mk_within_at_limit(rng):
    """Every value EXACTLY on its limit. Six comparisons that look like breaches and are not,
    because every limit here is inclusive -- except the season count, which is why this case sets
    the applications one BELOW the maximum rather than on it."""
    v = _base(rng)
    v["rate_proposed_l_per_ha"] = v["max_rate_l_per_ha"]
    v["distance_to_water_m"] = v["buffer_to_water_m"]
    v["days_to_harvest"] = v["pre_harvest_interval_days"]
    v["planned_re_entry_hours"] = v["re_entry_interval_hours"]
    v["applications_made_this_season"] = v["max_applications_per_season"] - 1
    if v["applications_made_this_season"] == 0:
        v["days_since_last_application"] = None
    else:
        v["days_since_last_application"] = v["min_retreatment_interval_days"]
    return _decoy_previous(v)


def _decoy_previous(v):
    """⚑ THE SECOND DECOY, SET ON EVERY `within_label` CASE. The previous season's count is chosen
    so that ADDING it to this season's would cross the label maximum. It is part of no check --
    the maximum is per season -- so a reader who adds them refuses an application that is inside
    the label, and this corpus makes that reachable on every clean case rather than on none."""
    v["previous_season_applications"] = (v["max_applications_per_season"]
                                         - v["applications_made_this_season"] + 1)
    return v


def _mk_crop_not_permitted(rng):
    """The permitted list carries the NEAR NEIGHBOUR of the proposed crop, and not the crop."""
    for _ in range(400):
        v = _base(rng)
        permitted = [c.strip() for c in v["permitted_crops"].split(",")]
        here = v["crop_proposed"]
        pair = next((p for p in CROP_PAIRS if here in p), None)
        if pair is None:
            continue
        twin = pair[1] if pair[0] == here else pair[0]
        if twin in permitted:
            continue
        v["crop_proposed"] = twin              # the label permits `here`, the proposal names `twin`
        return v
    raise RuntimeError("crop_not_permitted: exhausted")


def _mk_rate_over_max(rng):
    """One rung above the maximum -- a near miss, not an absurd one."""
    for _ in range(400):
        v = _base(rng)
        over = _up(RATES, v["max_rate_l_per_ha"])
        if over is None:
            continue
        v["rate_proposed_l_per_ha"] = over
        return v
    raise RuntimeError("rate_over_max: exhausted")


def _mk_season_max_reached(rng, rate_at_limit=False):
    """The off-by-one. `applications already made this season` EQUALS the label maximum, so this
    proposal would be the next one and is over it. On some of these the rate sits exactly on its
    own maximum, which IS inside -- the two readings of a limit on one page."""
    v = _base(rng)
    v["applications_made_this_season"] = v["max_applications_per_season"]
    v["days_since_last_application"] = (v["min_retreatment_interval_days"]
                                        + rng.choice([0, 4, 11]))
    if rate_at_limit:
        v["rate_proposed_l_per_ha"] = v["max_rate_l_per_ha"]
    v["previous_season_applications"] = 0
    return v


def _mk_tank_mix_prohibited(rng):
    for _ in range(400):
        v = _base(rng)
        prohibited = [p.strip() for p in v["tank_mix_prohibited_with"].split(",")]
        if v["tank_mix_prohibited_with"] == "none" or not prohibited:
            continue
        v["tank_mix_partner"] = rng.choice(prohibited)
        return v
    raise RuntimeError("tank_mix_prohibited: exhausted")


def _mk_buffer_too_small(rng):
    for _ in range(400):
        v = _base(rng)
        if v["buffer_to_water_m"] <= 1:
            continue
        v["distance_to_water_m"] = v["buffer_to_water_m"] - rng.choice([1, 2])
        return v
    raise RuntimeError("buffer_too_small: exhausted")


def _mk_retreatment_short(rng):
    for _ in range(400):
        v = _base(rng)
        if v["applications_made_this_season"] == 0:
            continue
        v["days_since_last_application"] = max(0, v["min_retreatment_interval_days"]
                                               - rng.choice([1, 3, 6]))
        return v
    raise RuntimeError("retreatment_short: exhausted")


def _mk_phi_short(rng):
    for _ in range(400):
        v = _base(rng)
        if v["pre_harvest_interval_days"] <= 7:
            continue
        v["days_to_harvest"] = max(0, v["pre_harvest_interval_days"] - rng.choice([1, 4, 9]))
        return v
    raise RuntimeError("phi_short: exhausted")


def _mk_rei_short(rng):
    """⚑ THE UNIT TRAP. The re-entry interval is the only restriction on the label in HOURS. This
    case sets the label's interval to one of the LARGER hour values and leaves the day counts
    comfortably satisfied, so a reader comparing the number without its unit -- 48 against a
    48-day harvest window -- clears it, and a reader who then answers `wait_required` anyway lands
    on the right verdict while naming the wrong restriction."""
    for _ in range(400):
        v = _base(rng)
        rei = rng.choice([24, 48])
        v["re_entry_interval_hours"] = rei
        v["planned_re_entry_hours"] = rei - rng.choice([6, 12, 18])
        v["days_to_harvest"] = max(v["pre_harvest_interval_days"], rei)
        if v["planned_re_entry_hours"] < 0:
            continue
        return v
    raise RuntimeError("rei_short: exhausted")


def _mk_hard_and_timing(rng, which):
    """A HARD restriction and a TIMING one, both breached. Precedence decides: the answer is
    `outside_label` naming the hard one, and a reader who stops at the first date they recognise
    answers `wait_required` -- telling a grower to wait before making an application that must not
    be made at all."""
    for _ in range(400):
        if which == "rate":
            v = _mk_rate_over_max(rng)
            if v["pre_harvest_interval_days"] <= 7:
                continue
            v["days_to_harvest"] = v["pre_harvest_interval_days"] - 3
        elif which == "crop":
            v = _mk_crop_not_permitted(rng)
            if v["applications_made_this_season"] == 0:
                continue
            v["days_since_last_application"] = max(0, v["min_retreatment_interval_days"] - 2)
        elif which == "season":
            v = _mk_season_max_reached(rng)
            v["planned_re_entry_hours"] = max(0, v["re_entry_interval_hours"] - 6)
        else:                                       # buffer
            v = _mk_buffer_too_small(rng)
            if v["pre_harvest_interval_days"] <= 7:
                continue
            v["days_to_harvest"] = v["pre_harvest_interval_days"] - 5
        return v
    raise RuntimeError("hard_and_timing(%s): exhausted" % which)


def _mk_label_silent(rng, which):
    """The label extract does not state the interval this proposal turns on. Everything ahead of it
    in the walk passes, so the answer is `insufficient_information` naming that restriction -- not
    a pass, and not a guess at what an unstated interval probably is."""
    for _ in range(400):
        v = _base(rng)
        if which == "min_retreatment_interval_days":
            if v["applications_made_this_season"] == 0:
                continue                            # the check would be skipped, not unreadable
            v["min_retreatment_interval_days"] = None
            v["days_since_last_application"] = rng.choice([4, 9, 16, 25])
        elif which == "pre_harvest_interval_days":
            v["pre_harvest_interval_days"] = None
        else:
            v["re_entry_interval_hours"] = None
        return v
    raise RuntimeError("label_silent(%s): exhausted" % which)


def _mk_proposal_silent(rng):
    """The other side of the page: the label states its pre-harvest interval and the proposal does
    not say when harvest is."""
    v = _base(rng)
    v["days_to_harvest"] = None
    return v


MAKERS = {
    "within_ordinary": _mk_within_ordinary,
    "within_at_limit": _mk_within_at_limit,
    "crop_not_permitted": _mk_crop_not_permitted,
    "rate_over_max": _mk_rate_over_max,
    "season_max_reached": _mk_season_max_reached,
    "tank_mix_prohibited": _mk_tank_mix_prohibited,
    "buffer_too_small": _mk_buffer_too_small,
    "retreatment_short": _mk_retreatment_short,
    "phi_short": _mk_phi_short,
    "rei_short": _mk_rei_short,
    "proposal_silent": _mk_proposal_silent,
}

EXPECTED = {
    "within_ordinary": ("within_label", "none"),
    "within_at_limit": ("within_label", "none"),
    "crop_not_permitted": ("outside_label", "permitted_crops"),
    "rate_over_max": ("outside_label", "max_rate_per_application"),
    "season_max_reached": ("outside_label", "max_applications_per_season"),
    "tank_mix_prohibited": ("outside_label", "tank_mix_prohibited"),
    "buffer_too_small": ("outside_label", "buffer_to_water"),
    "retreatment_short": ("wait_required", "min_retreatment_interval"),
    "phi_short": ("wait_required", "pre_harvest_interval"),
    "rei_short": ("wait_required", "re_entry_interval"),
    "proposal_silent": ("insufficient_information", "pre_harvest_interval"),
}
HARD_AND_TIMING_EXPECTED = {
    "rate": ("outside_label", "max_rate_per_application"),
    "crop": ("outside_label", "permitted_crops"),
    "season": ("outside_label", "max_applications_per_season"),
    "buffer": ("outside_label", "buffer_to_water"),
}
LABEL_SILENT_EXPECTED = {
    "min_retreatment_interval_days": ("insufficient_information", "min_retreatment_interval"),
    "pre_harvest_interval_days": ("insufficient_information", "pre_harvest_interval"),
    "re_entry_interval_hours": ("insufficient_information", "re_entry_interval"),
}
# At least this many of the season bucket must ALSO sit exactly on the rate maximum -- the case
# where an inclusive limit and an exclusive one are read off the same page.
N_SEASON_RATE_AT_LIMIT = 2
HARD_AND_TIMING_ORDER = ["rate", "crop", "season", "buffer"]
LABEL_SILENT_ORDER = ["pre_harvest_interval_days", "pre_harvest_interval_days",
                      "min_retreatment_interval_days", "re_entry_interval_hours"]

FIELD_ORDER = [
    "field_id", "permitted_crops", "max_rate_l_per_ha", "max_applications_per_season",
    "min_retreatment_interval_days", "pre_harvest_interval_days", "re_entry_interval_hours",
    "buffer_to_water_m", "tank_mix_prohibited_with", "crop_proposed", "rate_proposed_l_per_ha",
    "applications_made_this_season", "days_since_last_application", "days_to_harvest",
    "planned_re_entry_hours", "distance_to_water_m", "tank_mix_partner",
    "previous_season_applications", "application_status", "agronomist_note",
    "verdict", "deciding_restriction",
]


def _label_block(v):
    def line(name, value, unit, silent_text):
        if value is None:
            return "%s: %s" % (name, silent_text)
        return "%s: %s%s" % (name, _fmt(value), (" " + unit) if unit else "")
    return "\n".join([
        "permitted crops: %s" % v["permitted_crops"],
        line("maximum rate per application", v["max_rate_l_per_ha"], "L/ha", ""),
        line("maximum applications per season", v["max_applications_per_season"], "", ""),
        line("minimum re-treatment interval", v["min_retreatment_interval_days"], "days",
             "not stated on this label extract"),
        line("pre-harvest interval", v["pre_harvest_interval_days"], "days",
             "not stated on this label extract"),
        line("re-entry interval", v["re_entry_interval_hours"], "hours",
             "not stated on this label extract"),
        line("minimum buffer to surface water", v["buffer_to_water_m"], "m", ""),
        "tank mix prohibited with: %s" % v["tank_mix_prohibited_with"],
    ])


def _proposal_block(v):
    days_since = ("no application made to this crop this season"
                  if v["days_since_last_application"] is None
                  else "%s" % _fmt(v["days_since_last_application"]))
    dth = ("not stated in the proposal" if v["days_to_harvest"] is None
           else "%s" % _fmt(v["days_to_harvest"]))
    return "\n".join([
        "crop: %s" % v["crop_proposed"],
        "rate: %s L/ha" % _fmt(v["rate_proposed_l_per_ha"]),
        "applications already made this season: %s" % _fmt(v["applications_made_this_season"]),
        "days since the last application: %s" % days_since,
        "days to harvest: %s" % dth,
        "planned re-entry: %s hours after application" % _fmt(v["planned_re_entry_hours"]),
        "distance to nearest surface water: %s m" % _fmt(v["distance_to_water_m"]),
        "tank mix partner: %s" % v["tank_mix_partner"],
    ])


def build_all(rng, n=N_RECORDS):
    spec = list(BUCKETS)
    if n != N_RECORDS:                       # a --n other than the design keeps the shape, roughly
        spec = [(name, max(1, round(count * n / N_RECORDS))) for name, count in BUCKETS]
    buckets = _deal(rng, n, spec)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    applied = _deal(rng, n, [("applied", N_APPLIED), ("planned", n - N_APPLIED)])

    hat_left = list(HARD_AND_TIMING_ORDER)
    silent_left = list(LABEL_SILENT_ORDER)
    season_rate_left = N_SEASON_RATE_AT_LIMIT

    stats = {"verdicts": {}, "restrictions": {}, "buckets": {b: 0 for b, _ in BUCKETS},
             "ambiguous": 0, "needs_hold": 0, "previous_would_flip": 0,
             "season_rate_at_limit": 0, "confusable_interval": 0}

    out = []
    for i in range(1, n + 1):
        bucket = buckets[i - 1]
        if bucket == "hard_and_timing":
            which = hat_left.pop(0) if hat_left else "rate"
            v = _mk_hard_and_timing(rng, which)
            want = HARD_AND_TIMING_EXPECTED[which]
        elif bucket == "label_silent":
            which = silent_left.pop(0) if silent_left else "pre_harvest_interval_days"
            v = _mk_label_silent(rng, which)
            want = LABEL_SILENT_EXPECTED[which]
        elif bucket == "season_max_reached":
            at_limit = season_rate_left > 0
            season_rate_left -= 1
            v = _mk_season_max_reached(rng, rate_at_limit=at_limit)
            want = EXPECTED[bucket]
        else:
            v = MAKERS[bucket](rng)
            want = EXPECTED[bucket]

        d = CK.decide(v)
        assert (d["verdict"], d["deciding_restriction"]) == want, \
            "%s produced %r, not %r" % (bucket, (d["verdict"], d["deciding_restriction"]), want)

        rec_id = "LBL-%04d" % i
        field_id = "FLD-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                      rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                      rng.randint(10000, 99999))
        product = rng.choice(PRODUCTS)
        registration = "REG-20%02d-%05d" % (rng.randint(11, 24), rng.randint(10000, 99999))
        active = rng.choice(ACTIVES)
        grams = rng.choice([90, 100, 120, 150, 200, 250, 300, 360, 400, 450, 480])

        status = applied[i - 1]
        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the verdict normally, and contradicts it when ambiguous.
        calm = (d["verdict"] == "within_label") if not ambiguous else (d["verdict"] != "within_label")
        note = rng.choice(CALM_NOTES if calm else WORRIED_NOTES)

        v["field_id"] = field_id
        v["application_status"] = status
        v["agronomist_note"] = note
        v["verdict"] = d["verdict"]
        v["deciding_restriction"] = d["deciding_restriction"]

        lines = [
            _underline("Field"), field_id, "",
            _underline("Product and Registration"),
            "%s -- registration %s -- active substance %s %d g/L"
            % (product, registration, active, grams), "",
            _underline("Label Restrictions"), _label_block(v), "",
            _underline("Proposed Application"), _proposal_block(v), "",
            _underline("Season History"),
            "applications made in the PREVIOUS season: %s"
            % _fmt(v["previous_season_applications"]), "",
            _underline("Application Status"), status, "",
            _underline("Agronomist Notes"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {"case_id": rec_id}
        gold.update({k: v[k] for k in FIELD_ORDER})
        out.append((rec_id, text, gold, bucket))

        stats["verdicts"][d["verdict"]] = stats["verdicts"].get(d["verdict"], 0) + 1
        stats["restrictions"][d["deciding_restriction"]] = \
            stats["restrictions"].get(d["deciding_restriction"], 0) + 1
        stats["buckets"][bucket] += 1
        if d["verdict"] != "within_label" and status == "applied":
            stats["needs_hold"] += 1
        if (v["applications_made_this_season"] + v["previous_season_applications"]
                > v["max_applications_per_season"]
                and v["applications_made_this_season"] < v["max_applications_per_season"]):
            stats["previous_would_flip"] += 1
        if (bucket == "season_max_reached"
                and v["rate_proposed_l_per_ha"] == v["max_rate_l_per_ha"]):
            stats["season_rate_at_limit"] += 1
        if d["deciding_restriction"] in ("min_retreatment_interval", "pre_harvest_interval",
                                         "re_entry_interval"):
            stats["confusable_interval"] += 1
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the case it labels, and every gold verdict AND deciding
    restriction must be that case's own walk of the check set. A corpus whose labels are not
    readable off its own text is not a corpus, it is a second opinion."""
    for rec_id, text, gold, _bucket in rows:
        for field in ("field_id", "permitted_crops", "crop_proposed", "tank_mix_prohibited_with",
                      "tank_mix_partner", "application_status", "agronomist_note"):
            assert str(gold[field]) in text, "%s: %s not stated in the case" % (rec_id, field)
        for field in ("max_rate_l_per_ha", "max_applications_per_season", "buffer_to_water_m",
                      "rate_proposed_l_per_ha", "applications_made_this_season",
                      "planned_re_entry_hours", "distance_to_water_m",
                      "previous_season_applications"):
            assert _fmt(gold[field]) in text, "%s: %s not stated in the case" % (rec_id, field)

        for field, phrase in (("min_retreatment_interval_days", "not stated on this label extract"),
                              ("pre_harvest_interval_days", "not stated on this label extract"),
                              ("re_entry_interval_hours", "not stated on this label extract")):
            if gold[field] is None:
                assert phrase in text, "%s: null %s not explained" % (rec_id, field)
            else:
                assert _fmt(gold[field]) in text, "%s: %s not stated" % (rec_id, field)
        if gold["days_since_last_application"] is None:
            assert "no application made to this crop this season" in text, \
                "%s: null days_since_last_application not explained" % rec_id
        if gold["days_to_harvest"] is None:
            assert "not stated in the proposal" in text, \
                "%s: null days_to_harvest not explained" % rec_id

        d = CK.decide(gold)
        assert gold["verdict"] == d["verdict"], \
            "%s: gold verdict %r disagrees with its own walk (%r)" \
            % (rec_id, gold["verdict"], d["verdict"])
        assert gold["deciding_restriction"] == d["deciding_restriction"], \
            "%s: gold deciding_restriction %r disagrees with its own walk (%r)" \
            % (rec_id, gold["deciding_restriction"], d["deciding_restriction"])
        assert (gold["deciding_restriction"] == "none") == (gold["verdict"] == "within_label"), \
            "%s: `none` and within_label must agree in both directions" % rec_id


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
    print("cases: %d   bytes: %d" % (len(rows), total))
    print("verdicts: %s" % "  ".join("%s=%d" % (k, v)
                                     for k, v in sorted(stats["verdicts"].items())))
    print("deciding restrictions: %s"
          % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["restrictions"].items())))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["buckets"].items()))
    print("%d (%.0f%%) carry an agronomist note whose TONE contradicts the walk of the check set"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d case(s) turn on one of the THREE CONFUSABLE INTERVALS -- re-treatment, pre-harvest, "
          "re-entry (the last in hours)" % stats["confusable_interval"])
    print("%d case(s) would flip to a refusal if the PREVIOUS season's applications were added to "
          "this season's -- they are not part of any check" % stats["previous_would_flip"])
    print("%d case(s) sit exactly on the rate maximum AND over the season maximum -- an inclusive "
          "limit and an exclusive one on one page" % stats["season_rate_at_limit"])
    print("%d case(s) are not inside the label AND have already been applied -- the pure-code "
          "hold flag" % stats["needs_hold"])
    print("internal consistency check: PASSED (every gold value is stated in its own case, every "
          "verdict and deciding restriction is that case's own walk of data/checks.json, every "
          "null is explained in the text)")


if __name__ == "__main__":
    main()
