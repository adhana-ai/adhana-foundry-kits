"""Candidate records for one message. Pure code, no model -- the step that decides whether this
kit can be pointed at a real vendor's correspondence at all.

⚑ WHY THIS EXISTS, SAME CLAIM AS data-match's block.py. Comparing one message against every open
record ever written is a different product from comparing it against the handful that could
plausibly be what it is about. Blocking is what makes that set small; it is also the step that can
silently lose the true match, because a candidate that is never generated can never be judged. That
recall cost is measured (`stats()`), not assumed.

THE KEYS, and why each one is cheap and imperfect:

    an explicit record id in the text     the strongest signal there is, but present in only
                                          about half of this corpus's messages on purpose
    an explicit SKU code in the text      narrows to one product, but several open records can
                                          share one SKU
    the product's plain-English name      the weakest key -- a substring match against the
                                          vendor's own product description, present when neither
                                          of the above is

Every key is scoped to the message's OWN vendor first (known the way a sender's address is known
in a real inbox) -- nothing here ever proposes a candidate from a different vendor.
"""
from src import normalise


def _vendor_skus(vendor):
    return {s["sku"]: s["description"] for s in vendor["open_skus"]}


def candidates(message, vendor, records_by_vendor_sku):
    """Every open record this message could plausibly be about, plus which key found each one."""
    text_norm = normalise.text(message["text"])
    raw = message["text"]
    skus = _vendor_skus(vendor)

    keys_hit = []
    matched = {}          # record_id -> record

    recid = normalise.find_recid(raw)
    if recid:
        for (vid, sku), recs in records_by_vendor_sku.items():
            if vid != vendor["id"]:
                continue
            for r in recs:
                if r["record_id"] == recid:
                    matched[r["record_id"]] = r
                    keys_hit.append("recid:%s" % recid)

    for sku_code in normalise.find_skus(raw):
        if sku_code in skus:
            for r in records_by_vendor_sku.get((vendor["id"], sku_code), []):
                matched[r["record_id"]] = r
            keys_hit.append("sku:%s" % sku_code)

    for sku_code, desc in skus.items():
        if desc and desc in text_norm:
            for r in records_by_vendor_sku.get((vendor["id"], sku_code), []):
                matched[r["record_id"]] = r
            keys_hit.append("desc:%s" % sku_code)

    return {"candidates": sorted(matched.values(), key=lambda r: r["record_id"]),
           "keys_hit": keys_hit}


def stats(messages, vendors_by_id, records_by_vendor_sku, gold_by_id):
    """What blocking bought and what it cost, over the whole corpus -- the recall figure belongs
    on the report beside whatever accuracy the model earns downstream of it."""
    total_true = 0
    surviving = 0
    sizes = []
    for m in messages:
        g = gold_by_id.get(m["message_id"])
        if not g or g["matched_record_id"] == "NONE":
            continue
        total_true += 1
        v = vendors_by_id[m["vendor_id"]]
        c = candidates(m, v, records_by_vendor_sku)
        sizes.append(len(c["candidates"]))
        if any(r["record_id"] == g["matched_record_id"] for r in c["candidates"]):
            surviving += 1
    return {"messages_with_a_true_match": total_true, "true_match_surviving_blocking": surviving,
           "blocking_recall": round(surviving / total_true, 4) if total_true else None,
           "candidate_set_size_avg": round(sum(sizes) / len(sizes), 2) if sizes else None,
           "candidate_set_size_max": max(sizes) if sizes else None}
