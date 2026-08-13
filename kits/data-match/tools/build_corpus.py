#!/usr/bin/env python3
"""Generate the corpus and the labelled pair set from a fixed seed.

    python3 tools/build_corpus.py

Writes data/records.csv and data/labelled.jsonl, byte-identical on every run. Nothing is fetched and
nothing is licensed from anybody: the records are invented here, so the corpus ships under this
repo's MIT licence and there is no third-party grant to verify. See data/SOURCES.md.

⚑ THE TRAPS ARE PLANTED, NOT HOPED FOR. A corpus that cannot express the failure cannot show the
eval layer earning its keep, so every hard case this kit claims to measure is generated on purpose
and counted:

    nickname          Kathryn -> Kate, with the surname intact
    abbreviation      Rd / Road, St / Street, Ave / Avenue on the same address
    surname change    a married or hyphenated surname, both spellings in use
    transposed dob    04-08 and 08-04, one digit pair swapped
    email variant     the same person's address written two ways

    ...and the hard NEGATIVES, which are the ones that matter:

    relative          two people, one address, same surname and first initial, different dob
    twin              same address, same dob, first names one letter apart
    namesake          the identical name, everything else different

⚠︎ AND THE PLANTED ONE MUST BE THE ONLY ONE — THIS IS WHERE THE LAST KIT WENT WRONG. UC010's
generator drew 400 names from a pool of 280 combinations and produced 117 accidental duplicate
display names under a comment claiming exactly one was planted. Nobody noticed until the eval
started scoring collisions nobody had designed. So this file draws identities WITHOUT REPLACEMENT
from an explicit cross product, and then `audit()` asserts the census: every accidental collision is
a build failure, not a curiosity. If you widen the pools, the assertions are what tell you the
corpus still says what the README says it says.

⚠︎ NORMALISATION IS NOT DONE HERE AND MUST NOT BE. It is tempting to emit already-tidy records so
the numbers look better; that would delete the use case. The mess IS the input.
"""
import csv
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS = os.path.join(HERE, "data", "records.csv")
LABELS = os.path.join(HERE, "data", "labelled.jsonl")

SEED = 20260812
N_PEOPLE = 200
N_DUPLICATES = 60          # people who appear twice
N_RELATIVES = 12           # hard negative: one address, shared surname + initial
N_TWINS = 6                # hard negative: one address, one dob, names a letter apart
N_NAMESAKES = 10           # hard negative: identical name, nothing else shared
N_EASY_NEG = 32            # unrelated pairs, so the set is not all hard cases

FIRST = ["Kathryn", "Daniel", "Amelia", "Riley", "Jonathan", "Priya", "Marcus", "Elena",
         "Tobias", "Nadia", "Oliver", "Freya", "Idris", "Martha", "Callum", "Yusuf",
         "Rosalind", "Bernard", "Simone", "Hector", "Imani", "Lucia", "Rowan", "Delia",
         "Anselm", "Beatrix", "Cormac", "Dahlia", "Emrys", "Fenella", "Gideon", "Harriet",
         "Ignatius", "Jocasta", "Kester", "Lysander", "Morwenna", "Nathaniel", "Ottoline",
         "Peregrine", "Quintin", "Ravenna", "Sabine", "Thaddeus", "Ursula", "Verity",
         "Wilhelmina", "Xavier", "Yolanda", "Zachary"]
LAST = ["Muller", "Okonkwo", "Brennan", "Chen", "Whitfield", "Nakamura", "Adeyemi", "Voss",
        "Kowalski", "Farrell", "Aldridge", "Bhatt", "Castellano", "Duarte", "Eriksen",
        "Fitzgerald", "Grimaldi", "Halvorsen", "Iqbal", "Jankowski", "Kalinowski", "Lindqvist",
        "Marchetti", "Novak", "Oyelaran", "Pemberton", "Quintero", "Rasmussen", "Sandoval",
        "Thackeray", "Ulyanov", "Vasquez", "Wickham", "Yamamoto", "Zielinski", "Achebe",
        "Blackwood", "Carrington", "Delacroix", "Esposito"]
STREETS = ["Ferndale", "Bridge", "Larch", "Kiln", "Alder", "Harrow", "Sable", "Corvid",
           "Quarry", "Marlow", "Pennine", "Thistle", "Ashcombe", "Bellweather", "Cinder",
           "Drover", "Elmsworth", "Fallow", "Garnet", "Hollybank", "Ironside", "Juniper",
           "Kestrel", "Linden", "Moorgate", "Netherby", "Orchard", "Pilgrim"]
# ⚑ THE SUFFIX PAIRS ARE THE ABBREVIATION TRAP AND THEY LIVE HERE, NOT IN THE NORMALISER. The
# normaliser is allowed to know that "Rd" and "Road" are the same word. Nothing in this kit is
# allowed to know that "Kate" and "Kathryn" are the same person — that is the judgement the model is
# being paid for, and teaching it to the floor would flatter the floor and hide the finding.
SUFFIX = [("Rd", "Road"), ("St", "Street"), ("Ave", "Avenue"), ("Ln", "Lane"), ("Cl", "Close")]
NICK = {"Kathryn": "Kate", "Daniel": "Dan", "Amelia": "Amy", "Jonathan": "Jon",
        "Marcus": "Marc", "Tobias": "Toby", "Oliver": "Ollie", "Martha": "Mattie",
        "Rosalind": "Roz", "Bernard": "Bernie", "Harriet": "Hattie", "Nathaniel": "Nate",
        "Beatrix": "Trixie", "Peregrine": "Perry", "Zachary": "Zach", "Wilhelmina": "Mina"}
MARRIED = ["Brennan-Ward", "Chen-Adeyemi", "Voss-Farrell", "Bhatt-Lindqvist"]


def email_for(first, last, style=0):
    f, l = first.lower(), last.lower().replace("-", ".")
    return ["%s.%s@example.com" % (f, l),
            "%s%s@example.com" % (f[0], l),
            "%s.%s@example.net" % (f[0], l),
            "%s_%s@example.com" % (f, l)][style % 4]


def build():
    rng = random.Random(SEED)

    # Identities drawn WITHOUT REPLACEMENT from the explicit cross product. This is the line that
    # makes the census assertable — sampling with replacement is what produced UC010's 117.
    combos = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(combos)
    # ⚠︎ THE POOL IS SIZED AGAINST WHAT IS DRAWN, NOT AGAINST N_PEOPLE. The namesakes take addresses
    # from past the end of the people block, so 28 streets x 8 numbers (224) raised IndexError at the
    # 25th namesake — the same class of bug as drawing names from too small a pool, caught here by an
    # exception rather than by a silent collision only because these are indexed and those were not.
    addresses = ["%d %s %s" % (n, s, suf[0])
                 for s in STREETS
                 for n in (3, 5, 9, 14, 22, 27, 33, 41, 47, 58, 64, 72, 79, 88, 91, 96)
                 for suf in [SUFFIX[0]]]
    rng.shuffle(addresses)

    people, records, pairs = [], [], []
    rid = 0

    def add(person_id, first, last, dob, addr, email, note=""):
        nonlocal rid
        rid += 1
        r = {"id": "r%03d" % rid, "person_id": person_id, "name": "%s %s" % (first, last),
             "dob": dob, "address": addr, "email": email}
        records.append(r)
        return r

    for i in range(N_PEOPLE):
        first, last = combos[i]
        dob = "%d-%02d-%02d" % (rng.randint(1955, 2002), rng.randint(1, 12), rng.randint(1, 28))
        addr = addresses[i]
        people.append({"pid": "p%03d" % (i + 1), "first": first, "last": last,
                       "dob": dob, "addr": addr})
        add("p%03d" % (i + 1), first, last, dob, addr, email_for(first, last, 0))

    # ── the duplicates: the same person, entered again, differently ────────────────────────────────
    dup_targets = list(range(N_PEOPLE))
    rng.shuffle(dup_targets)
    dup_targets = dup_targets[:N_DUPLICATES]
    traps = []
    for n, idx in enumerate(dup_targets):
        p = people[idx]
        first, last, dob, addr = p["first"], p["last"], p["dob"], p["addr"]
        trap = ["nickname", "abbreviation", "surname-change", "transposed-dob", "email-variant"][n % 5]
        if trap == "nickname":
            first = NICK.get(first, first[:3])
        elif trap == "abbreviation":
            for short, long in SUFFIX:
                if addr.endswith(" " + short):
                    addr = addr[: -len(short)] + long
                    break
        elif trap == "surname-change":
            last = MARRIED[n % len(MARRIED)] if rng.random() < 0.5 else last + "-" + \
                LAST[(idx + 7) % len(LAST)]
        elif trap == "transposed-dob":
            y, m, d = dob.split("-")
            # only transposable when both halves are valid months/days, or the record is a lie
            if int(d) <= 12:
                dob = "%s-%s-%s" % (y, d, m)
            else:
                trap = "email-variant"
        b = add(p["pid"], first, last, dob, addr, email_for(first, last, 1 + (n % 3)))
        a = next(r for r in records if r["person_id"] == p["pid"] and r["id"] != b["id"])
        pairs.append({"a": a["id"], "b": b["id"], "label": "same", "trap": trap})
        traps.append(trap)

    # ── hard negatives ────────────────────────────────────────────────────────────────────────────
    free = [i for i in range(N_PEOPLE) if i not in dup_targets]
    rng.shuffle(free)
    cur = 0

    # ⚠︎ EVERY INVENTED NAME IS CHECKED AGAINST WHAT IS ALREADY IN USE. The first version picked a
    # relative's forename by initial alone and produced two full-name collisions with unrelated
    # people — 'Marcus Blackwood' twice, in different families. That is the accidental-namesake defect
    # arriving by the back door: the identity pool was drawn without replacement, and then this block
    # invented new identities without consulting it.
    used = {(r["name"].split(" ")[0], " ".join(r["name"].split(" ")[1:])) for r in records}

    def fresh_first(initial, last, unlike):
        for f in FIRST:
            if f[0] == initial and f != unlike and (f, last) not in used:
                return f
        for f in FIRST:                                # any unused name beats a duplicate identity
            if f != unlike and (f, last) not in used:
                return f
        raise SystemExit("name pool exhausted for surname %r — widen FIRST" % last)

    for _ in range(N_RELATIVES):                      # one address, shared surname + initial
        p = people[free[cur]]; cur += 1
        first2 = fresh_first(p["first"][0], p["last"], p["first"])
        used.add((first2, p["last"]))
        y = int(p["dob"][:4]) - rng.randint(22, 34)
        dob2 = "%d-%s" % (y, p["dob"][5:])
        pid = "p%03d" % (len(people) + 1)
        people.append({"pid": pid, "first": first2, "last": p["last"], "dob": dob2,
                       "addr": p["addr"]})
        b = add(pid, first2, p["last"], dob2, p["addr"], email_for(first2, p["last"], 2))
        a = next(r for r in records if r["person_id"] == p["pid"])
        pairs.append({"a": a["id"], "b": b["id"], "label": "different", "trap": "relative"})

    for _ in range(N_TWINS):                          # one address, one dob, a letter apart
        p = people[free[cur]]; cur += 1
        first2 = p["first"][:-1] + ("e" if not p["first"].endswith("e") else "a")
        if (first2, p["last"]) in used:               # a twin must not become somebody else
            first2 = fresh_first(p["first"][0], p["last"], p["first"])
        used.add((first2, p["last"]))
        pid = "p%03d" % (len(people) + 1)
        people.append({"pid": pid, "first": first2, "last": p["last"], "dob": p["dob"],
                       "addr": p["addr"]})
        b = add(pid, first2, p["last"], p["dob"], p["addr"], email_for(first2, p["last"], 0))
        a = next(r for r in records if r["person_id"] == p["pid"])
        pairs.append({"a": a["id"], "b": b["id"], "label": "different", "trap": "twin"})

    for _ in range(N_NAMESAKES):                      # the identical name, nothing else
        p = people[free[cur]]; cur += 1
        dob2 = "%d-%02d-%02d" % (rng.randint(1955, 2002), rng.randint(1, 12), rng.randint(1, 28))
        addr2 = addresses[N_PEOPLE + cur]
        pid = "p%03d" % (len(people) + 1)
        people.append({"pid": pid, "first": p["first"], "last": p["last"], "dob": dob2,
                       "addr": addr2})
        b = add(pid, p["first"], p["last"], dob2, addr2, email_for(p["first"], p["last"], 3))
        a = next(r for r in records if r["person_id"] == p["pid"])
        pairs.append({"a": a["id"], "b": b["id"], "label": "different", "trap": "namesake"})

    # ── easy negatives, so the set is not exclusively hard ─────────────────────────────────────────
    seen = {(p["a"], p["b"]) for p in pairs}
    while sum(1 for p in pairs if p["trap"] == "unrelated") < N_EASY_NEG:
        a, b = rng.sample(records, 2)
        if a["person_id"] == b["person_id"] or (a["id"], b["id"]) in seen:
            continue
        seen.add((a["id"], b["id"]))
        pairs.append({"a": a["id"], "b": b["id"], "label": "different", "trap": "unrelated"})

    for i, p in enumerate(pairs):
        p["id"] = "q%03d" % (i + 1)
    return records, pairs


def audit(records, pairs):
    """The census, asserted. A number in the README that no code checks is a number that goes wrong."""
    problems = []
    names = {}
    for r in records:
        names.setdefault(r["name"], []).append(r)

    # ⚑ THE RULE IS ABOUT PEOPLE, NOT ROWS, AND THE FIRST VERSION OF THIS CHECK GOT IT WRONG — it
    # reported 38 "accidental" collisions that were all correct. Two rows may share a display name for
    # two entirely legitimate reasons: they are the SAME person entered twice (the `email-variant` and
    # `transposed-dob` traps deliberately leave the name alone — that is what makes them hard), or
    # they are a planted `namesake`. A collision is only an accident when it spans person_ids that
    # nobody planted. ⚠︎ Worth keeping as a note rather than a silent fix: a census check that cries
    # wolf gets switched off, and then the real 117-collision defect ships behind it.
    planted = {(p["a"], p["b"]) for p in pairs if p["trap"] == "namesake"}
    planted |= {(b, a) for a, b in planted}
    for name, rows in sorted(names.items()):
        if len(rows) < 2:
            continue
        pids = {r["person_id"] for r in rows}
        if len(pids) == 1:
            continue                       # one person, entered twice — the point of the corpus
        ok = all(any((x["id"], y["id"]) in planted for y in rows if y is not x) for x in rows)
        if not ok:
            problems.append("accidental shared display name %r across %s (person_ids %s)"
                            % (name, sorted(r["id"] for r in rows), sorted(pids)))

    ids = [r["id"] for r in records]
    if len(set(ids)) != len(ids):
        problems.append("duplicate record ids")
    for p in pairs:
        if p["a"] == p["b"]:
            problems.append("pair %s compares a record with itself" % p["id"])
    same = sum(1 for p in pairs if p["label"] == "same")
    diff = len(pairs) - same
    counts = {}
    for p in pairs:
        counts[p["trap"]] = counts.get(p["trap"], 0) + 1
    return problems, {"records": len(records), "pairs": len(pairs), "same": same,
                      "different": diff, "traps": counts}


def main():
    records, pairs = build()
    problems, census = audit(records, pairs)

    print("CORPUS — seed %d, deterministic\n" % SEED)
    print("  records            %d" % census["records"])
    print("  labelled pairs     %d   (%d same / %d different)"
          % (census["pairs"], census["same"], census["different"]))
    print("  balance            %.0f%% same — stated, because a matcher scored on a mostly-different"
          % (100.0 * census["same"] / census["pairs"]))
    print("                     set can look excellent by answering 'different' to everything")
    print("\n  planted traps")
    for k, v in sorted(census["traps"].items()):
        print("    %-16s %d" % (k, v))

    if problems:
        print("\nAUDIT FAILED — %d problem(s). The corpus does not say what the README says it says:"
              % len(problems))
        for p in problems[:12]:
            print("  - %s" % p)
        raise SystemExit(1)
    print("\n  audit             clean — every shared display name is one that was planted")

    with open(RECORDS, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "person_id", "name", "dob", "address", "email"])
        w.writeheader()
        for r in records:
            w.writerow(r)
    with open(LABELS, "w", encoding="utf-8") as fh:
        for p in pairs:
            fh.write(json.dumps({"id": p["id"], "a": p["a"], "b": p["b"],
                                 "label": p["label"], "trap": p["trap"]}, sort_keys=True) + "\n")
    print("\nwrote data/records.csv and data/labelled.jsonl")


if __name__ == "__main__":
    main()
