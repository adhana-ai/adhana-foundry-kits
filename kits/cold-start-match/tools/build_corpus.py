"""Build the whole corpus from a fixed seed. No network, no third-party data -- run it and the
corpus is byte-identical every time.

    python3 tools/build_corpus.py

Writes data/history.jsonl (prior comparable items with a recorded early-sales outcome),
data/requests.jsonl (new-item setup requests with no sales history of their own), and
data/gold.jsonl (the pairwise LIKE_ITEM / NOT_LIKE_ITEM ground truth, mechanically derived from
the SAME rule stated in src/prompt.py's RULES text -- see `is_like_item()` below, which is that
rule in code rather than in prose, so the two cannot silently drift apart).

⚑ WHY SHAPED ITEMS, NOT PURELY RANDOM ONES. A purely random corpus would make a true comparable
item a rare accident -- four independent categorical fields agreeing (or agreeing within the
stated allowances) by chance is unlikely, and an eval with almost no positive cases proves nothing
about recall. So each request gets a deliberately PLANTED set of comparable items (some exact, some
exercising the two allowances -- an adjacent price tier, an ecommerce-family channel swap) and a
deliberately planted set of near-misses (each violating exactly one rule). Everything else in the
category pool is random filler. `is_like_item()` is applied uniformly afterward, so a filler item
that happens to satisfy the rule by coincidence is labelled LIKE_ITEM too -- nothing is
hand-labelled.
"""
import json
import os
import random

SEED = 20260818
random.seed(SEED)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

CATEGORIES = ["cookware", "small-appliances", "outdoor-furniture", "bath-textiles", "pet-supplies"]
MATERIALS = ["stainless_steel", "cast_iron", "ceramic", "hard_plastic", "glass"]
PRICE_TIERS = ["value", "core", "premium", "luxury"]               # ORDER MATTERS -- adjacency
CHANNELS = ["ecommerce_only", "marketplace", "big_box", "specialty_store", "club_store"]
ECOMM_FAMILY = {"ecommerce_only", "marketplace"}
SEASONS = ["back_to_school", "holiday", "summer", "spring", "year_round"]

REQUESTS_PER_CATEGORY = 3
FILLER_PER_CATEGORY = 3

NOTES_POOL = [
    "ran alongside a supplier lead-time change on the same category",
    "vendor swapped a component mid-run",
    "first time this material shipped in this channel",
    "overlapped a planogram reset",
    "",  # most items carry no note at all
    "", "", "",
]

MERCHANT_NOTES = [
    "merchant flags this as similar to last year's line",
    "brand-new vendor, no direct sales history of its own",
    "competitor stocks something similar in this channel",
    "finance asked for a conservative estimate on this one",
    "",
    "",
]


def _price_case(price_tier):
    if price_tier == "value":
        return round(random.uniform(3, 9), 2), random.randint(24, 48)
    if price_tier == "core":
        return round(random.uniform(10, 24), 2), random.randint(12, 36)
    if price_tier == "premium":
        return round(random.uniform(25, 59), 2), random.randint(6, 24)
    return round(random.uniform(60, 150), 2), random.randint(4, 12)          # luxury


_MATERIAL_BASE_UNITS = {"stainless_steel": 18.0, "cast_iron": 14.0, "ceramic": 16.0,
                        "hard_plastic": 22.0, "glass": 12.0}
_SEASON_BUMP = {"back_to_school": 3.0, "holiday": 6.0, "summer": 2.0, "spring": 1.0,
               "year_round": 0.0}
_CHANNEL_BUMP = {"ecommerce_only": 1.0, "marketplace": 4.0, "big_box": 6.0,
                 "specialty_store": 2.0, "club_store": 5.0}
_PRICE_TIER_MULT = {"value": 1.3, "core": 1.0, "premium": 0.75, "luxury": 0.5}


def _wk13_units(material, season, channel, price_tier):
    base = (_MATERIAL_BASE_UNITS[material] + _SEASON_BUMP[season] + _CHANNEL_BUMP[channel])
    base *= _PRICE_TIER_MULT[price_tier]
    base += random.uniform(-3, 3)
    return round(max(1.0, base), 1)


def _tier_neighbor(tier):
    i = PRICE_TIERS.index(tier)
    choices = [j for j in (i - 1, i + 1) if 0 <= j < len(PRICE_TIERS)]
    return PRICE_TIERS[random.choice(choices)] if choices else tier


def _tier_two_away(tier):
    i = PRICE_TIERS.index(tier)
    choices = [j for j in range(len(PRICE_TIERS)) if abs(j - i) >= 2]
    return PRICE_TIERS[random.choice(choices)] if choices else PRICE_TIERS[(i + 2) % len(PRICE_TIERS)]


def _ecomm_partner(channel):
    return next(c for c in ECOMM_FAMILY if c != channel)


def is_like_item(request, item):
    """The LIKE_ITEM rule -- identical to src/prompt.py's RULES text, in code. The single source
    both gold generation and (indirectly, via the prompt) the model are held to."""
    if request["material"] != item["material"]:
        return False
    ri, ei = PRICE_TIERS.index(request["price_tier"]), PRICE_TIERS.index(item["price_tier"])
    if abs(ri - ei) > 1:
        return False
    rc, ec = request["channel"], item["channel"]
    if rc != ec and not (rc in ECOMM_FAMILY and ec in ECOMM_FAMILY):
        return False
    if request["season"] != item["season"]:
        return False
    return True


def _random_item(iid, category):
    mat = random.choice(MATERIALS)
    tier = random.choice(PRICE_TIERS)
    price, case_pack = _price_case(tier)
    channel = random.choice(CHANNELS)
    season = random.choice(SEASONS)
    return {"item_id": iid, "category": category, "material": mat, "price_tier": tier,
           "channel": channel, "season": season, "unit_price_usd": price,
           "case_pack_qty": case_pack,
           "wk13_units_per_store": _wk13_units(mat, season, channel, tier),
           "notes": random.choice(NOTES_POOL)}


def _random_request(rid, category):
    mat = random.choice(MATERIALS)
    tier = random.choice(PRICE_TIERS)
    price, case_pack = _price_case(tier)
    return {"request_id": rid, "category": category, "material": mat, "price_tier": tier,
           "channel": random.choice(CHANNELS), "season": random.choice(SEASONS),
           "unit_price_usd": price, "case_pack_qty": case_pack,
           "merchant_note": random.choice(MERCHANT_NOTES)}


def _planted_like_items(request, ids):
    """Three deliberate comparables: one exact, one exercising the price-tier allowance, one
    exercising the ecommerce-family allowance (falling back to a second exact match when the
    request's own channel is not in the ecommerce family)."""
    out = []
    # 1. exact on every material field.
    price, case_pack = _price_case(request["price_tier"])
    out.append({"item_id": ids[0], "category": request["category"], "material": request["material"],
               "price_tier": request["price_tier"], "channel": request["channel"],
               "season": request["season"], "unit_price_usd": price, "case_pack_qty": case_pack,
               "wk13_units_per_store": _wk13_units(request["material"], request["season"],
                                                   request["channel"], request["price_tier"]),
               "notes": random.choice(NOTES_POOL)})
    # 2. adjacent price tier, everything else exact -- the tier-allowance trap.
    price, case_pack = _price_case(request["price_tier"])
    tier2 = _tier_neighbor(request["price_tier"])
    out.append({"item_id": ids[1], "category": request["category"], "material": request["material"],
               "price_tier": tier2, "channel": request["channel"], "season": request["season"],
               "unit_price_usd": price, "case_pack_qty": case_pack,
               "wk13_units_per_store": _wk13_units(request["material"], request["season"],
                                                   request["channel"], tier2),
               "notes": random.choice(NOTES_POOL)})
    # 3. ecommerce-family swap if applicable, else a second exact match -- the channel-family trap.
    channel3 = (_ecomm_partner(request["channel"])
               if request["channel"] in ECOMM_FAMILY else request["channel"])
    price, case_pack = _price_case(request["price_tier"])
    out.append({"item_id": ids[2], "category": request["category"], "material": request["material"],
               "price_tier": request["price_tier"], "channel": channel3, "season": request["season"],
               "unit_price_usd": price, "case_pack_qty": case_pack,
               "wk13_units_per_store": _wk13_units(request["material"], request["season"],
                                                   channel3, request["price_tier"]),
               "notes": random.choice(NOTES_POOL)})
    return out


def _planted_nearmiss(request, ids):
    """Four deliberate near-misses, each violating exactly one rule -- straightforward negatives
    that keep the labelled set from being all positives on the shaped side."""
    out = []
    # violates material only
    other_mat = random.choice([m for m in MATERIALS if m != request["material"]])
    price, case_pack = _price_case(request["price_tier"])
    out.append({"item_id": ids[0], "category": request["category"], "material": other_mat,
               "price_tier": request["price_tier"], "channel": request["channel"],
               "season": request["season"], "unit_price_usd": price, "case_pack_qty": case_pack,
               "wk13_units_per_store": _wk13_units(other_mat, request["season"],
                                                   request["channel"], request["price_tier"]),
               "notes": random.choice(NOTES_POOL)})
    # violates price tier only (two apart -- outside the adjacency allowance)
    price, case_pack = _price_case(request["price_tier"])
    tier2 = _tier_two_away(request["price_tier"])
    out.append({"item_id": ids[1], "category": request["category"], "material": request["material"],
               "price_tier": tier2, "channel": request["channel"], "season": request["season"],
               "unit_price_usd": price, "case_pack_qty": case_pack,
               "wk13_units_per_store": _wk13_units(request["material"], request["season"],
                                                   request["channel"], tier2),
               "notes": random.choice(NOTES_POOL)})
    # violates channel only, to a non-family channel
    other_c = random.choice([c for c in CHANNELS if c != request["channel"]
                            and not (c in ECOMM_FAMILY and request["channel"] in ECOMM_FAMILY)])
    price, case_pack = _price_case(request["price_tier"])
    out.append({"item_id": ids[2], "category": request["category"], "material": request["material"],
               "price_tier": request["price_tier"], "channel": other_c, "season": request["season"],
               "unit_price_usd": price, "case_pack_qty": case_pack,
               "wk13_units_per_store": _wk13_units(request["material"], request["season"],
                                                   other_c, request["price_tier"]),
               "notes": random.choice(NOTES_POOL)})
    # violates season only
    other_s = random.choice([s for s in SEASONS if s != request["season"]])
    price, case_pack = _price_case(request["price_tier"])
    out.append({"item_id": ids[3], "category": request["category"], "material": request["material"],
               "price_tier": request["price_tier"], "channel": request["channel"], "season": other_s,
               "unit_price_usd": price, "case_pack_qty": case_pack,
               "wk13_units_per_store": _wk13_units(request["material"], other_s,
                                                   request["channel"], request["price_tier"]),
               "notes": random.choice(NOTES_POOL)})
    return out


def build():
    history, requests = [], []
    it_n, rq_n = 1, 1
    for cat in CATEGORIES:
        cat_items = []
        for _ in range(REQUESTS_PER_CATEGORY):
            rid = "NEW-%05d" % rq_n
            rq_n += 1
            req = _random_request(rid, cat)
            requests.append(req)

            aid = ["ITM-%05d" % (it_n + k) for k in range(3)]
            it_n += 3
            cat_items += _planted_like_items(req, aid)

            nid = ["ITM-%05d" % (it_n + k) for k in range(4)]
            it_n += 4
            cat_items += _planted_nearmiss(req, nid)

        for _ in range(FILLER_PER_CATEGORY):
            iid = "ITM-%05d" % it_n
            it_n += 1
            cat_items.append(_random_item(iid, cat))

        history.extend(cat_items)

    gold = []
    for req in requests:
        for it in history:
            if it["category"] != req["category"]:
                continue
            label = "like_item" if is_like_item(req, it) else "not_like_item"
            gold.append({"request_id": req["request_id"], "item_id": it["item_id"],
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

    n_like = sum(1 for g in gold if g["label"] == "like_item")
    print("history  : %d items across %d categories" % (len(history), len(CATEGORIES)))
    print("requests : %d" % len(requests))
    print("gold     : %d pairs, %d like_item (%.1f%%), %d not_like_item"
         % (len(gold), n_like, 100.0 * n_like / len(gold), len(gold) - n_like))


if __name__ == "__main__":
    main()
