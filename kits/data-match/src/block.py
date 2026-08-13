"""Candidate pairs. The step that decides whether this kit can be pointed at a real customer list.

⚑ THIS IS WHERE THE KIT BREAKS AT SCALE, AND IT IS THE ONE NUMBER A FORKER MUST SEE BEFORE THEY TRY IT
ON THEIR OWN DATA. Comparing every record with every other is n(n-1)/2 pairs: 288 records is 41,328
comparisons, 50,000 records is 1.25 BILLION. At one model call per pair that is not a budget problem,
it is a different product. Blocking is what makes the number finite — only records that share a cheap
key are compared at all — and it is also the step that can silently lose true matches, because a pair
that is never generated can never be judged.

⚠︎ SO THE RECALL COST OF BLOCKING IS MEASURED, NOT ASSUMED. `stats()` reports how many of the labelled
SAME pairs survive the blocking keys. A blocker that quietly drops 10% of true matches sets a ceiling
on every score downstream, and no amount of model quality can recover it — the model is never shown the
pair. That ceiling belongs in the report, next to the accuracy it caps.

THE KEYS, and why each one is cheap and imperfect:

    dob digits        two records of one person usually agree on the date, however it is written
    last name + house the surname plus the street number, which survives Rd/Road and flat numbers
    email local part  the part before the @, which survives a provider change

A pair is a candidate if it shares ANY key. That is a union, deliberately: each key alone misses a
different trap, and the cheapest way to raise recall is another key rather than a cleverer one.
"""
import itertools

from src import normalise


def keys(record):
    """The cheap keys for one record. Any shared key makes a pair a candidate."""
    f = normalise.fields(record)
    out = set()
    d = f["dob"]["norm"]
    if d:
        out.add("dob:%s" % d)
    parts = f["name"]["norm"].split()
    house = f["address"]["norm"].split()[0] if f["address"]["norm"] else ""
    if parts and house:
        out.add("name-house:%s|%s" % (parts[-1], house))
    local = f["email"]["norm"].split("@")[0]
    if local:
        out.add("email:%s" % local)
    return out


def candidates(records):
    """Every pair sharing at least one key, as (id_a, id_b) with a stable order."""
    buckets = {}
    for r in records:
        for k in keys(r):
            buckets.setdefault(k, []).append(r["id"])
    pairs = set()
    for ids in buckets.values():
        for a, b in itertools.combinations(sorted(set(ids)), 2):
            pairs.add((a, b))
    return sorted(pairs)


def stats(records, labelled=None):
    """What blocking bought and what it cost. Both halves, always — the saving is meaningless without
    the recall it paid for."""
    n = len(records)
    everything = n * (n - 1) // 2
    cand = candidates(records)
    out = {"records": n, "all_pairs": everything, "candidate_pairs": len(cand),
           "reduction": round(1 - (len(cand) / everything), 4) if everything else 0.0}
    if labelled:
        want = {(min(p["a"], p["b"]), max(p["a"], p["b"]))
                for p in labelled if p["label"] == "same"}
        got = want & set(cand)
        out["true_pairs"] = len(want)
        out["true_pairs_surviving"] = len(got)
        out["blocking_recall"] = round(len(got) / len(want), 4) if want else 0.0
        out["lost_to_blocking"] = sorted(want - got)
    return out
