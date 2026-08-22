#!/usr/bin/env python3
"""Generate synthetic bulk-tank pre-load check sheets and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one check sheet per file) and data/gold.jsonl, byte-identical on every
run. Every tank id, terminal name and inspector note here is invented; every cargo name is an
ordinary generic chemical or oil name. Nothing is fetched and nothing is licensed from anybody, so
the corpus ships under this repo's MIT licence.

⚠︎ NO COMMERCIAL, INDUSTRY-BODY OR PROPRIETARY COMPATIBILITY CHART IS REPRODUCED. The matrix this
corpus is built against is `data/matrix.json`, which was written for this kit and is illustrative
rather than authoritative. See data/SOURCES.md.

⚑ GOLD `verdict` IS A MATRIX LOOKUP, NOT A LABEL SOMEBODY TYPED. It is derived from the same five
structured values the generator itself decided, with the same rule the kit publishes everywhere
else -- src/matrix.py::decide(), which src/prompt.py states to the model in words and
evals/judge.py re-runs over the model's own reply. It is never derived from the inspector's note,
and the note never feeds the label.

⚑ THE FOUR CHECKS, AND WHY THEY HAVE A STOPPING ORDER. Is the prior cargo even known; is the pair
reactive; is the predecessor banned for this grade over its own look-back depth; and only then,
did the CERTIFICATE meet the minimum wash. Each of the four hard buckets below exists because a
reader who skips one of those steps, or takes them out of order, gets that bucket wrong:

  refuse_banned_prior   -- a prior cargo that is chemically compatible, water-soluble and trivially
                           rinsed out, and banned anyway (methanol before a food-grade load).
                           Cleaning does not cure a ban.
  clean_cert_wrong      -- the tank log claims a thorough wash and the CERTIFICATE covers a lower
                           regime. The certificate governs, so the tank is credited with the lower
                           one. Reading the log line gives `accept`; reading the certificate gives
                           `clean_then_load`.
  refuse_banned_twoback -- an entirely innocuous prior cargo, and the cargo BEHIND it is banned.
                           Food grade and high purity read two back; technical grade does not.
  accept_alarming       -- a corrosive heel (caustic, acid, hypochlorite) that sounds alarming and
                           is water-soluble, so an ordinary rinse genuinely clears it. What is
                           expensive to clean here is fat and hydrocarbon, not corrosives.

⚑ THE PLANTED AMBIGUITY: the verdict is a matrix lookup, and the terminal inspector's own note
disagrees with it on `N_AMBIGUOUS` of sheets. A tank that must be refused carries a relaxed note
("Tank presented clean and dry, no odour on opening. Nothing of concern."); a tank that is
genuinely fine carries a note that reads as though something is wrong with it. Anything that
classifies off the note's TONE -- including evals/baseline.py, deliberately -- fails those sheets
by construction. Anything that runs the matrix gets them right.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import matrix as MX                       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 55

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the fix a sibling kit in
# this series had to make after its first generator asked for 40 pct ambiguity and delivered 51.
# A count 1.7 standard deviations off its own design is not a corpus property, it is sampling
# noise being published as one. So every bucket here is a fixed COUNT, shuffled by the seeded RNG.
BUCKETS = [
    ("accept_ordinary", 10),        # verdict accept, nothing alarming about the pair
    ("accept_alarming", 6),         # a corrosive heel that SOUNDS bad and rinses out fine
    ("clean_cert_wrong", 8),        # the log claims enough, the CERTIFICATE covers less
    ("clean_undercleaned", 7),      # the tank simply has not been cleaned to the standard
    ("refuse_reactive", 6),         # a reactive heel/product pair -- no cleaning clears it
    ("refuse_banned_prior", 7),     # a predecessor banned for this grade, cleaning irrelevant
    ("refuse_banned_twoback", 5),   # innocuous prior cargo, banned cargo BEHIND it
    ("undetermined", 6),            # no prior cargo recorded -- nothing to check against
]
N_AMBIGUOUS = 22                    # 40 pct, exactly -- an inspector note from the wrong register
N_LOADED = 24                       # load_status == "loaded"; the rest are still "pending"

# Invented terminals and berths. Nothing here is a real terminal, operator or berth.
TERMINALS = [
    ("North Quay Terminal", "Berth 4"),
    ("Saltmarsh Jetty", "Berth 2"),
    ("Eastgate Tank Farm", "Berth 7"),
    ("Lowdock Terminal", "Berth 1"),
    ("Kingsferry Wharf", "Berth 9"),
    ("Old Basin Terminal", "Berth 3"),
]

GRADES = ("technical", "food_grade", "high_purity")

# What can plausibly be loaded AS each grade. Kept small and obvious so a reader can see the corpus
# is a construction, and so no combination reads as advice about a real product.
INCOMING_BY_GRADE = {
    "food_grade": ["refined soybean oil", "refined sunflower oil", "refined rapeseed oil",
                   "refined coconut oil", "propylene glycol", "ethanol"],
    "high_purity": ["isopropanol", "acetone", "ethylene glycol", "methyl ethyl ketone",
                    "phosphoric acid"],
    "technical": ["sodium hydroxide solution", "sulphuric acid", "toluene", "xylene", "base oil",
                  "gas oil", "acetic acid", "hydrochloric acid", "sodium hypochlorite solution",
                  "ethanol", "propylene glycol", "white mineral oil"],
}

# Notes whose TONE says "this tank is fine to load". Used truthfully on a sheet whose verdict is
# `accept`, and against type on one that is not -- half the planted ambiguity.
CALM_NOTES = [
    "Tank presented clean and dry, no odour on opening. Nothing of concern.",
    "Routine turnaround for this berth. Cleaning paperwork looked in order to me.",
    "No issues noted at the hatch. Happy for this one to go ahead.",
    "Standard changeover, nothing unusual about this unit at all.",
]

# Notes whose TONE says "something is wrong with this tank". Used truthfully on a sheet whose
# verdict is not `accept`, and against type on one that is fine -- the other half.
WORRIED_NOTES = [
    "Faint odour still present at the hatch -- escalated to the duty superintendent.",
    "Not confident about this changeover; asked for the paperwork to be reviewed again.",
    "Something looked off in the tank record, flagged for a second look before loading.",
    "Previous cargo history on this unit is disputed; under manual audit this week.",
]

WASHES = list(MX.WASH_LADDER)                       # none .. steam_and_dry
CERTIFIABLE = [w for w in WASHES if w != "none"]    # a certificate cannot certify "no wash"
ALARMING_CLASSES = ("caustic", "acid", "oxidiser")


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


def _cargoes_of(cls):
    return list(MX.M["classes"][cls])


def _safe_prior_classes(grade):
    """Classes that are NOT banned as a predecessor for this grade."""
    banned = set(MX.M["banned_predecessor_classes"].get(grade) or [])
    return [c for c in MX.M["classes"] if c not in banned]


def _pick_prior(rng, grade, classes):
    """A cargo of one of `classes` that is not banned by NAME for this grade either."""
    for _ in range(500):
        cargo = rng.choice(_cargoes_of(rng.choice(classes)))
        if not MX.is_banned_predecessor(cargo, grade):
            return cargo
    raise RuntimeError("no unbanned prior cargo for grade %r in %r" % (grade, classes))


def _pick_incoming(rng, grade, prior, forbid_reactive=True):
    for _ in range(500):
        prod = rng.choice(INCOMING_BY_GRADE[grade])
        if forbid_reactive and MX.is_reactive(prior, prod):
            continue
        return prod
    raise RuntimeError("no incoming product for grade %r after %r" % (grade, prior))


def _pick_two_back(rng, grade, banned):
    """A cargo behind the prior one. `banned` picks whether it must be barred for this grade."""
    pool = [c for cls in MX.M["classes"] for c in _cargoes_of(cls)]
    hits = [c for c in pool if MX.is_banned_predecessor(c, grade) == banned]
    if not hits:
        return None
    return rng.choice(hits)


def _rank(w):
    return MX.WASH_RANK[w]


def _credited(cert):
    return "none" if cert == "not_certified" else cert


# --------------------------------------------------------------------------------------------
# One constructor per bucket. Each returns the five decision values plus wash_performed, and each
# is ASSERTED against the matrix at the end of build_all -- a constructor that quietly stops
# producing its own bucket is exactly the defect an exact composition exists to prevent.
# --------------------------------------------------------------------------------------------

def _mk_accept_ordinary(rng):
    grade = rng.choice(GRADES)
    classes = [c for c in _safe_prior_classes(grade) if c not in ALARMING_CLASSES]
    prior = _pick_prior(rng, grade, classes)
    incoming = _pick_incoming(rng, grade, prior)
    two_back = _pick_two_back(rng, grade, banned=False) if rng.random() < 0.7 else None
    required = MX.minimum_wash(prior, grade)
    cert = WASHES[min(len(WASHES) - 1, _rank(required) + rng.choice([0, 0, 1]))]
    return incoming, grade, prior, two_back, cert, cert


def _mk_accept_alarming(rng):
    """A corrosive heel that sounds alarming and washes out with an ordinary rinse."""
    for _ in range(2000):
        cls = rng.choice(ALARMING_CLASSES)
        grade = "technical" if cls == "oxidiser" else rng.choice(["technical", "food_grade"])
        if cls in set(MX.M["banned_predecessor_classes"].get(grade) or []):
            continue
        prior = rng.choice(_cargoes_of(cls))
        if MX.is_banned_predecessor(prior, grade):
            continue
        incoming = _pick_incoming(rng, grade, prior)
        two_back = _pick_two_back(rng, grade, banned=False) if rng.random() < 0.6 else None
        required = MX.minimum_wash(prior, grade)
        cert = required                     # exactly the minimum, nothing more
        return incoming, grade, prior, two_back, cert, cert
    raise RuntimeError("accept_alarming: exhausted")


def _mk_clean_cert_wrong(rng):
    """The log claims a wash that WOULD have been enough; the certificate covers less."""
    for _ in range(4000):
        grade = rng.choice(GRADES)
        prior = _pick_prior(rng, grade, _safe_prior_classes(grade))
        required = MX.minimum_wash(prior, grade)
        if _rank(required) < 2:
            continue                        # no room for a certificate strictly below it
        incoming = _pick_incoming(rng, grade, prior)
        two_back = _pick_two_back(rng, grade, banned=False) if rng.random() < 0.6 else None
        performed = rng.choice([w for w in WASHES if _rank(w) >= _rank(required)])
        lower = [w for w in CERTIFIABLE if _rank(w) < _rank(required)] + ["not_certified"]
        cert = rng.choice(lower)
        return incoming, grade, prior, two_back, cert, performed
    raise RuntimeError("clean_cert_wrong: exhausted")


def _mk_clean_undercleaned(rng):
    """The tank simply has not been cleaned to the standard, and its paperwork agrees."""
    for _ in range(4000):
        grade = rng.choice(GRADES)
        prior = _pick_prior(rng, grade, _safe_prior_classes(grade))
        required = MX.minimum_wash(prior, grade)
        if _rank(required) < 1:
            continue
        incoming = _pick_incoming(rng, grade, prior)
        two_back = _pick_two_back(rng, grade, banned=False) if rng.random() < 0.6 else None
        lower = [w for w in CERTIFIABLE if _rank(w) < _rank(required)] + ["not_certified"]
        cert = rng.choice(lower)
        performed = _credited(cert)         # the log and the certificate agree here
        return incoming, grade, prior, two_back, cert, performed
    raise RuntimeError("clean_undercleaned: exhausted")


def _mk_refuse_reactive(rng):
    for _ in range(4000):
        pair = rng.choice(MX.M["reactive_pairs"])
        a, b = (pair["a"], pair["b"]) if rng.random() < 0.5 else (pair["b"], pair["a"])
        prior = rng.choice(_cargoes_of(a))
        incoming_pool = [c for c in INCOMING_BY_GRADE["technical"] if MX.class_of(c) == b]
        if not incoming_pool:
            continue
        incoming = rng.choice(incoming_pool)
        grade = "technical"
        if MX.is_banned_predecessor(prior, grade):
            continue
        two_back = _pick_two_back(rng, grade, banned=False) if rng.random() < 0.6 else None
        cert = rng.choice(CERTIFIABLE)
        return incoming, grade, prior, two_back, cert, cert
    raise RuntimeError("refuse_reactive: exhausted")


def _mk_refuse_banned_prior(rng, force_methanol=False):
    """A predecessor banned for this grade. The tank is CLEAN to the standard and it does not help."""
    for _ in range(4000):
        grade = "food_grade" if force_methanol else rng.choice(["food_grade", "high_purity"])
        banned_pool = [c for cls in MX.M["classes"] for c in _cargoes_of(cls)
                       if MX.is_banned_predecessor(c, grade)]
        prior = "methanol" if force_methanol else rng.choice(banned_pool)
        incoming = _pick_incoming(rng, grade, prior)
        if MX.is_reactive(prior, incoming):
            continue
        two_back = _pick_two_back(rng, grade, banned=False) if rng.random() < 0.6 else None
        required = MX.minimum_wash(prior, grade)
        cert = WASHES[min(len(WASHES) - 1, _rank(required) + rng.choice([0, 1]))]
        return incoming, grade, prior, two_back, cert, cert
    raise RuntimeError("refuse_banned_prior: exhausted")


def _mk_refuse_banned_twoback(rng):
    """Innocuous prior cargo, certified to the standard -- and the cargo BEHIND it is banned."""
    for _ in range(4000):
        grade = rng.choice(["food_grade", "high_purity"])
        prior = _pick_prior(rng, grade, _safe_prior_classes(grade))
        incoming = _pick_incoming(rng, grade, prior)
        if MX.is_reactive(prior, incoming):
            continue
        two_back = _pick_two_back(rng, grade, banned=True)
        if two_back is None:
            continue
        required = MX.minimum_wash(prior, grade)
        cert = WASHES[min(len(WASHES) - 1, _rank(required) + rng.choice([0, 1]))]
        # ⚑ THE POINT OF THE BUCKET, ASSERTED HERE RATHER THAN HOPED FOR: with the two-back cargo
        # hidden, this sheet reads as a clean `accept`. Everything that makes it a refusal is one
        # cargo further back than a careless reader looks.
        if MX.required_action(incoming, grade, prior, None, cert) != "accept":
            continue
        return incoming, grade, prior, two_back, cert, cert
    raise RuntimeError("refuse_banned_twoback: exhausted")


def _mk_undetermined(rng):
    """No prior cargo recorded. Nothing to check the incoming product against."""
    grade = rng.choice(GRADES)
    incoming = rng.choice(INCOMING_BY_GRADE[grade])
    two_back = _pick_two_back(rng, grade, banned=False) if rng.random() < 0.5 else None
    cert = rng.choice(CERTIFIABLE + ["not_certified"])
    performed = _credited(cert)
    return incoming, grade, None, two_back, cert, performed


MAKERS = {
    "accept_ordinary": _mk_accept_ordinary,
    "accept_alarming": _mk_accept_alarming,
    "clean_cert_wrong": _mk_clean_cert_wrong,
    "clean_undercleaned": _mk_clean_undercleaned,
    "refuse_reactive": _mk_refuse_reactive,
    "refuse_banned_prior": _mk_refuse_banned_prior,
    "refuse_banned_twoback": _mk_refuse_banned_twoback,
    "undetermined": _mk_undetermined,
}

EXPECTED_VERDICT = {
    "accept_ordinary": "accept",
    "accept_alarming": "accept",
    "clean_cert_wrong": "clean_then_load",
    "clean_undercleaned": "clean_then_load",
    "refuse_reactive": "refuse",
    "refuse_banned_prior": "refuse",
    "refuse_banned_twoback": "refuse",
    "undetermined": "undetermined",
}

# At least this many of the refuse_banned_prior bucket must be the sharpest case in the matrix:
# methanol before a food-grade load. Water-miscible, non-reactive, trivially rinsed out, banned.
N_METHANOL_FOOD = 3


def build_all(rng, n=N_RECORDS):
    spec = list(BUCKETS)
    if n != N_RECORDS:                       # a --n other than the design keeps the shape, roughly
        spec = [(name, max(1, round(count * n / N_RECORDS))) for name, count in BUCKETS]
    buckets = _deal(rng, n, spec)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    loaded = _deal(rng, n, [("loaded", N_LOADED), ("pending", n - N_LOADED)])

    methanol_left = N_METHANOL_FOOD
    stats = {"verdicts": {}, "buckets": {name: 0 for name, _ in BUCKETS},
             "ambiguous": 0, "needs_hold": 0, "methanol_food": 0, "cert_below_log": 0}

    out = []
    for i in range(1, n + 1):
        bucket = buckets[i - 1]
        if bucket == "refuse_banned_prior" and methanol_left > 0:
            vals = _mk_refuse_banned_prior(rng, force_methanol=True)
            methanol_left -= 1
        else:
            vals = MAKERS[bucket](rng)
        incoming, grade, prior, two_back, cert, performed = vals

        d = MX.decide(incoming, grade, prior, two_back, cert)
        verdict = d["verdict"]
        assert verdict == EXPECTED_VERDICT[bucket], \
            "%s produced %r, not %r" % (bucket, verdict, EXPECTED_VERDICT[bucket])

        terminal, berth = rng.choice(TERMINALS)
        tank_id = "TNK-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                     rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                     rng.randint(10000, 99999))
        cert_ref = "CLC-%05d" % rng.randint(10000, 99999)

        status = loaded[i - 1]
        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the verdict normally, and contradicts it when ambiguous.
        calm = (verdict == "accept") if not ambiguous else (verdict != "accept")
        note = rng.choice(CALM_NOTES if calm else WORRIED_NOTES)

        prior_line = prior if prior is not None else "not recorded"
        two_back_line = (two_back if two_back is not None
                         else "none -- tank recertified before the prior cargo")
        cert_line = ("%s -- certified for: %s" % (cert_ref, cert)
                     if cert != "not_certified" else "no cleaning certificate on file")

        rec_id = "CGO-%04d" % i
        lines = [
            _underline("Tank"), tank_id, "",
            _underline("Terminal and Berth"), "%s, %s" % (terminal, berth), "",
            _underline("Incoming Product"), incoming, "",
            _underline("Incoming Grade"), grade, "",
            _underline("Prior Cargo"), prior_line, "",
            _underline("Two-Back Cargo"), two_back_line, "",
            _underline("Wash Performed"), performed, "",
            _underline("Cleaning Certificate"), cert_line, "",
            _underline("Load Status"), status, "",
            _underline("Inspector Notes"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "check_id": rec_id,
            "tank_id": tank_id,
            "incoming_product": incoming,
            "incoming_grade": grade,
            "prior_cargo": prior,
            "two_back_cargo": two_back,
            "wash_performed": performed,
            "wash_certified_for": cert,
            "load_status": status,
            "inspector_notes": note,
            "verdict": verdict,
        }
        out.append((rec_id, text, gold, bucket))

        stats["verdicts"][verdict] = stats["verdicts"].get(verdict, 0) + 1
        stats["buckets"][bucket] += 1
        if verdict != "accept" and status == "loaded":
            stats["needs_hold"] += 1
        if prior == "methanol" and grade == "food_grade":
            stats["methanol_food"] += 1
        if _rank(performed) > _rank(_credited(cert)):
            stats["cert_below_log"] += 1
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the sheet it labels, every gold verdict must be that
    sheet's own matrix lookup, and the two nullable fields must be null exactly when the sheet
    says so. A corpus whose labels are not readable off its own text is not a corpus, it is a
    second opinion."""
    for rec_id, text, gold, _bucket in rows:
        for field in ("tank_id", "incoming_product", "incoming_grade", "wash_performed",
                      "load_status", "inspector_notes"):
            assert gold[field] in text, "%s: %s not stated in the sheet" % (rec_id, field)

        if gold["prior_cargo"] is None:
            assert "not recorded" in text, "%s: null prior cargo not explained" % rec_id
        else:
            assert gold["prior_cargo"] in text, "%s: prior_cargo not stated" % rec_id
        if gold["two_back_cargo"] is None:
            assert "tank recertified" in text, "%s: null two-back cargo not explained" % rec_id
        else:
            assert gold["two_back_cargo"] in text, "%s: two_back_cargo not stated" % rec_id

        if gold["wash_certified_for"] == "not_certified":
            assert "no cleaning certificate on file" in text, \
                "%s: uncertified tank not stated" % rec_id
        else:
            assert "certified for: %s" % gold["wash_certified_for"] in text, \
                "%s: certificate regime not stated verbatim" % rec_id

        want = MX.required_action(gold["incoming_product"], gold["incoming_grade"],
                                  gold["prior_cargo"], gold["two_back_cargo"],
                                  gold["wash_certified_for"])
        assert gold["verdict"] == want, \
            "%s: gold verdict %r disagrees with its own matrix lookup (%r)" \
            % (rec_id, gold["verdict"], want)


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
    print("sheets: %d   bytes: %d" % (len(rows), total))
    print("verdicts: %s" % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["verdicts"].items())))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["buckets"].items()))
    print("%d (%.0f%%) carry an inspector note whose TONE contradicts the matrix verdict"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d sheet(s) have a certificate covering LESS than the tank log claims was performed"
          % stats["cert_below_log"])
    print("%d sheet(s) put methanol before a food-grade load -- compatible, washes out, banned"
          % stats["methanol_food"])
    print("%d sheet(s) are not clear-to-load AND already loaded -- the pure-code hold flag"
          % stats["needs_hold"])
    print("internal consistency check: PASSED (every gold value is stated in its own sheet, every "
          "verdict is that sheet's own matrix lookup, both nullable fields are explained in text)")


if __name__ == "__main__":
    main()
