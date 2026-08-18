"""Build the whole corpus from a fixed seed. No network, no third-party data -- run it and the
corpus is byte-identical every time.

    python3 tools/build_corpus.py

Writes data/history.jsonl (prior comparable events), data/requests.jsonl (planned requests to
estimate), and data/gold.jsonl (the pairwise ANALOG / NOT_ANALOG ground truth, mechanically
derived from the SAME rule stated in src/prompt.py's RULES text -- see `is_analog()` below, which
is that rule in code rather than in prose, so the two cannot silently drift apart).

⚑ WHY SHAPED EVENTS, NOT PURELY RANDOM ONES. A purely random corpus would make a true analog a
rare accident -- four independent categorical fields agreeing (or agreeing within the stated
allowances) by chance is unlikely, and an eval with almost no positive cases proves nothing about
recall. So each request gets a deliberately PLANTED set of analogs (some exact, some exercising the
two allowances -- an adjacent price band, a circular-placement swap) and a deliberately planted set
of near-misses (each violating exactly one rule). Everything else in the category pool is random
filler. `is_analog()` is applied uniformly afterward, so a filler event that happens to satisfy the
rule by coincidence is labelled ANALOG too -- nothing is hand-labelled.
"""
import json
import os
import random

SEED = 20260818
random.seed(SEED)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

CATEGORIES = ["snacks", "beverages", "personal-care", "home-goods", "seasonal-decor"]
MECHANICS = ["bogo", "pct_off", "dollar_off", "bundle", "gift_with_purchase"]
PRICE_BANDS = ["under_5", "5_10", "10_25", "25_plus"]              # ORDER MATTERS -- adjacency
AD_PLACEMENTS = ["circular_front", "circular_inside", "endcap", "digital_only", "email_only"]
CIRCULAR_FAMILY = {"circular_front", "circular_inside"}
SEASONS = ["back_to_school", "holiday", "summer", "spring", "none"]

REQUESTS_PER_CATEGORY = 3
FILLER_PER_CATEGORY = 3

NOTES_POOL = [
    "ran alongside a competitor stock-out on the same category",
    "extended by a few days due to a distribution delay",
    "coincided with a regional weather event that suppressed footfall",
    "first time this mechanic ran in this placement",
    "overlapped a national promotional calendar date",
    "",  # most events carry no note at all
    "", "", "",
]

PLANNER_NOTES = [
    "planner flags this as a repeat of last year's slot",
    "new SKU, no direct history of its own",
    "competitor is expected to run something similar the same week",
    "finance asked for a conservative estimate on this one",
    "",
    "",
]


def _mechanic_depth_duration(mechanic):
    if mechanic == "bogo":
        return 50, random.randint(5, 14)
    if mechanic == "pct_off":
        return random.randint(10, 40), random.randint(3, 21)
    if mechanic == "dollar_off":
        return random.randint(10, 30), random.randint(3, 14)
    if mechanic == "bundle":
        return random.randint(15, 35), random.randint(7, 21)
    return random.randint(10, 25), random.randint(5, 14)          # gift_with_purchase


_MECH_BASE_LIFT = {"bogo": 42, "pct_off": 22, "dollar_off": 15, "bundle": 28,
                   "gift_with_purchase": 20}
_SEASON_BUMP = {"back_to_school": 6, "holiday": 9, "summer": 3, "spring": 2, "none": 0}
_PLACEMENT_BUMP = {"circular_front": 8, "circular_inside": 4, "endcap": 6, "digital_only": 1,
                   "email_only": 0}


def _actual_lift(mechanic, season, placement, depth):
    base = _MECH_BASE_LIFT[mechanic] + _SEASON_BUMP[season] + _PLACEMENT_BUMP[placement]
    base += depth * 0.15
    base += random.uniform(-6, 6)
    return round(max(2.0, base), 1)


def _band_neighbor(band):
    i = PRICE_BANDS.index(band)
    choices = [j for j in (i - 1, i + 1) if 0 <= j < len(PRICE_BANDS)]
    return PRICE_BANDS[random.choice(choices)] if choices else band


def _band_two_away(band):
    i = PRICE_BANDS.index(band)
    choices = [j for j in range(len(PRICE_BANDS)) if abs(j - i) >= 2]
    return PRICE_BANDS[random.choice(choices)] if choices else PRICE_BANDS[(i + 2) % len(PRICE_BANDS)]


def _circular_partner(placement):
    return next(p for p in CIRCULAR_FAMILY if p != placement)


def is_analog(request, event):
    """The ANALOG rule -- identical to src/prompt.py's RULES text, in code. The single source both
    gold generation and (indirectly, via the prompt) the model are held to."""
    if request["mechanic"] != event["mechanic"]:
        return False
    ri, ei = PRICE_BANDS.index(request["price_band"]), PRICE_BANDS.index(event["price_band"])
    if abs(ri - ei) > 1:
        return False
    rp, ep = request["ad_placement"], event["ad_placement"]
    if rp != ep and not (rp in CIRCULAR_FAMILY and ep in CIRCULAR_FAMILY):
        return False
    if request["season"] != event["season"]:
        return False
    return True


def _random_event(eid, category):
    mech = random.choice(MECHANICS)
    depth, dur = _mechanic_depth_duration(mech)
    placement = random.choice(AD_PLACEMENTS)
    season = random.choice(SEASONS)
    band = random.choice(PRICE_BANDS)
    return {"event_id": eid, "category": category, "mechanic": mech, "price_band": band,
           "ad_placement": placement, "season": season, "discount_depth_pct": depth,
           "duration_days": dur, "actual_lift_pct": _actual_lift(mech, season, placement, depth),
           "notes": random.choice(NOTES_POOL)}


def _random_request(rid, category):
    mech = random.choice(MECHANICS)
    depth, dur = _mechanic_depth_duration(mech)
    return {"request_id": rid, "category": category, "mechanic": mech,
           "price_band": random.choice(PRICE_BANDS), "ad_placement": random.choice(AD_PLACEMENTS),
           "season": random.choice(SEASONS), "discount_depth_pct": depth, "duration_days": dur,
           "planner_note": random.choice(PLANNER_NOTES)}


def _planted_analogs(request, ids):
    """Three deliberate analogs: one exact, one exercising the price-band allowance, one
    exercising the circular-placement allowance (falling back to a second exact match when the
    request's own placement is not in the circular family)."""
    out = []
    # 1. exact on every material field.
    depth, dur = _mechanic_depth_duration(request["mechanic"])
    out.append({"event_id": ids[0], "category": request["category"], "mechanic": request["mechanic"],
               "price_band": request["price_band"], "ad_placement": request["ad_placement"],
               "season": request["season"], "discount_depth_pct": depth, "duration_days": dur,
               "actual_lift_pct": _actual_lift(request["mechanic"], request["season"],
                                               request["ad_placement"], depth),
               "notes": random.choice(NOTES_POOL)})
    # 2. adjacent price band, everything else exact -- the band-allowance trap.
    depth, dur = _mechanic_depth_duration(request["mechanic"])
    out.append({"event_id": ids[1], "category": request["category"], "mechanic": request["mechanic"],
               "price_band": _band_neighbor(request["price_band"]),
               "ad_placement": request["ad_placement"], "season": request["season"],
               "discount_depth_pct": depth, "duration_days": dur,
               "actual_lift_pct": _actual_lift(request["mechanic"], request["season"],
                                               request["ad_placement"], depth),
               "notes": random.choice(NOTES_POOL)})
    # 3. circular-family swap if applicable, else a second exact match -- the placement-family trap.
    placement3 = (_circular_partner(request["ad_placement"])
                 if request["ad_placement"] in CIRCULAR_FAMILY else request["ad_placement"])
    depth, dur = _mechanic_depth_duration(request["mechanic"])
    out.append({"event_id": ids[2], "category": request["category"], "mechanic": request["mechanic"],
               "price_band": request["price_band"], "ad_placement": placement3,
               "season": request["season"], "discount_depth_pct": depth, "duration_days": dur,
               "actual_lift_pct": _actual_lift(request["mechanic"], request["season"],
                                               placement3, depth),
               "notes": random.choice(NOTES_POOL)})
    return out


def _planted_nearmiss(request, ids):
    """Four deliberate near-misses, each violating exactly one rule -- straightforward negatives
    that keep the labelled set from being all positives on the shaped side."""
    out = []
    # violates mechanic only
    other_mech = random.choice([m for m in MECHANICS if m != request["mechanic"]])
    depth, dur = _mechanic_depth_duration(other_mech)
    out.append({"event_id": ids[0], "category": request["category"], "mechanic": other_mech,
               "price_band": request["price_band"], "ad_placement": request["ad_placement"],
               "season": request["season"], "discount_depth_pct": depth, "duration_days": dur,
               "actual_lift_pct": _actual_lift(other_mech, request["season"],
                                               request["ad_placement"], depth),
               "notes": random.choice(NOTES_POOL)})
    # violates price band only (two apart -- outside the adjacency allowance)
    depth, dur = _mechanic_depth_duration(request["mechanic"])
    out.append({"event_id": ids[1], "category": request["category"], "mechanic": request["mechanic"],
               "price_band": _band_two_away(request["price_band"]),
               "ad_placement": request["ad_placement"], "season": request["season"],
               "discount_depth_pct": depth, "duration_days": dur,
               "actual_lift_pct": _actual_lift(request["mechanic"], request["season"],
                                               request["ad_placement"], depth),
               "notes": random.choice(NOTES_POOL)})
    # violates placement only, to a non-family placement
    other_p = random.choice([p for p in AD_PLACEMENTS if p != request["ad_placement"]
                            and not (p in CIRCULAR_FAMILY and request["ad_placement"] in CIRCULAR_FAMILY)])
    depth, dur = _mechanic_depth_duration(request["mechanic"])
    out.append({"event_id": ids[2], "category": request["category"], "mechanic": request["mechanic"],
               "price_band": request["price_band"], "ad_placement": other_p,
               "season": request["season"], "discount_depth_pct": depth, "duration_days": dur,
               "actual_lift_pct": _actual_lift(request["mechanic"], request["season"], other_p, depth),
               "notes": random.choice(NOTES_POOL)})
    # violates season only
    other_s = random.choice([s for s in SEASONS if s != request["season"]])
    depth, dur = _mechanic_depth_duration(request["mechanic"])
    out.append({"event_id": ids[3], "category": request["category"], "mechanic": request["mechanic"],
               "price_band": request["price_band"], "ad_placement": request["ad_placement"],
               "season": other_s, "discount_depth_pct": depth, "duration_days": dur,
               "actual_lift_pct": _actual_lift(request["mechanic"], other_s,
                                               request["ad_placement"], depth),
               "notes": random.choice(NOTES_POOL)})
    return out


def build():
    history, requests = [], []
    ev_n, rq_n = 1, 1
    for cat in CATEGORIES:
        cat_events = []
        for _ in range(REQUESTS_PER_CATEGORY):
            rid = "REQ-%05d" % rq_n
            rq_n += 1
            req = _random_request(rid, cat)
            requests.append(req)

            aid = ["EVT-%05d" % (ev_n + k) for k in range(3)]
            ev_n += 3
            cat_events += _planted_analogs(req, aid)

            nid = ["EVT-%05d" % (ev_n + k) for k in range(4)]
            ev_n += 4
            cat_events += _planted_nearmiss(req, nid)

        for _ in range(FILLER_PER_CATEGORY):
            eid = "EVT-%05d" % ev_n
            ev_n += 1
            cat_events.append(_random_event(eid, cat))

        history.extend(cat_events)

    gold = []
    for req in requests:
        for ev in history:
            if ev["category"] != req["category"]:
                continue
            label = "analog" if is_analog(req, ev) else "not_analog"
            gold.append({"request_id": req["request_id"], "event_id": ev["event_id"],
                        "label": label})
    return history, requests, gold


def main():
    history, requests, gold = build()
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "history.jsonl"), "w", encoding="utf-8") as f:
        for h in history:
            f.write(json.dumps(h, ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "requests.jsonl"), "w", encoding="utf-8") as f:
        for r in requests:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    n_analog = sum(1 for g in gold if g["label"] == "analog")
    print("history  : %d events across %d categories" % (len(history), len(CATEGORIES)))
    print("requests : %d" % len(requests))
    print("gold     : %d pairs, %d analog (%.1f%%), %d not_analog"
         % (len(gold), n_analog, 100.0 * n_analog / len(gold), len(gold) - n_analog))


if __name__ == "__main__":
    main()
