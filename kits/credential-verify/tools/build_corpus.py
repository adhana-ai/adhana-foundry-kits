#!/usr/bin/env python3
"""Generate synthetic credentialing files and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one file per provider) and data/gold.jsonl, byte-identical on every
run. Every provider, license and PSV finding here is invented -- nothing is fetched and nothing
is licensed from anybody, so the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ GOLD IS DERIVED FROM THE GENERATED FILE TEXT, NEVER FROM A TARGET THAT SEEDED IT. The license
expiration/PSV-check dates and the adverse-action finding are read back off the actual generated
document, not carried over from a random draw.

⚑ THE PLANTED AMBIGUITY: this kit's guardrail is that ANY adverse action must be caught, however
mildly it is worded -- a "public reprimand" or "consent order" is an adverse action exactly like a
"revocation", even though it reads far more mildly. `AMBIGUOUS_FRACTION` of this corpus's adverse
findings are written in that mild, easy-to-miss phrasing; the rest use an unambiguous word like
"revoked" or "suspended". Gold always records the TRUE presence regardless of phrasing severity --
derived from which generator branch produced it, never re-derived from a scorer's or a model's own
reading of how serious the wording sounds.
"""
import argparse
import json
import os
import random
from datetime import date, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260821
N_FILES = 55

FIRST = ["Jordan", "Morgan", "Casey", "Riley", "Avery", "Priya", "Wei", "Fatima", "Diego",
         "Elena", "Marcus", "Nadia", "Owen", "Sofia", "Liam", "Amara", "Kenji", "Ines",
         "Tobias", "Yara", "Grace", "Malik", "Renata", "Anton"]
LAST = ["Alvarez", "Chen", "Okafor", "Petrov", "Nakamura", "Silva", "Kowalski", "Haddad",
        "Rossi", "Larsen", "Osei", "Fischer", "Reyes", "Novak", "Duarte", "Bergstrom",
        "Abara", "Tanaka", "Whitfield", "Correa"]
PSV_SOURCES = ["State Medical Board online licensure portal", "NPDB self-query report",
               "OIG-LEIE exclusion database", "State Board of Nursing licensure lookup"]
PROVIDER_TYPES = ["physician", "nurse_practitioner", "physician_assistant"]

PSV_LOOKBACK_DAYS = 180
AMBIGUOUS_FRACTION = 0.40
NO_ADVERSE_FRACTION = 0.55
EXPIRED_FRACTION = 0.15
STALE_PSV_FRACTION = 0.15


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _mild_adverse(rng):
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        return "Public reprimand issued 2025-04-12 for recordkeeping violation; license otherwise active and in good standing."
    if variant == 1:
        return "Consent order entered 2025-02-03 requiring a continuing-education course on documentation practices; no practice restriction imposed."
    return "Letter of concern issued 2025-06-20 regarding a single late chart-completion pattern; no further board action taken."


def _severe_adverse(rng):
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        return "License suspended 2025-05-01 pending investigation of a standard-of-care complaint."
    if variant == 1:
        return "Board action: license revoked 2025-03-15 following a disciplinary hearing."
    return "Excluded from federal healthcare program participation per OIG-LEIE, effective 2025-01-10."


def _clean_finding(rng):
    return rng.choice([
        "License active and in good standing. No board actions, sanctions or exclusions on file.",
        "No adverse action found. License current and unrestricted.",
        "Query returned no disciplinary history. License status: active.",
    ])


def build_all(rng, n=N_FILES):
    stats = {"adverse_present": 0, "adverse_mild": 0, "adverse_severe": 0, "clean": 0,
             "expired": 0, "stale_psv": 0}
    out = []
    for i in range(1, n + 1):
        name = "%s %s. %s" % (rng.choice(FIRST), rng.choice(LAST)[0], rng.choice(LAST))
        npi = "%010d" % rng.randint(1000000000, 1999999999)
        license_number = "%s-%06d" % (rng.choice(["MD", "NP", "PA"]), rng.randint(10000, 99999))
        provider_type = rng.choice(PROVIDER_TYPES)
        psv_source = rng.choice(PSV_SOURCES)

        effective = date(2026, rng.randint(3, 9), rng.randint(1, 25))
        credentialing_effective_date = effective.isoformat()

        is_expired = rng.random() < EXPIRED_FRACTION
        if is_expired:
            # expired 10-100 days BEFORE the effective date
            license_expiration_date = (effective - timedelta(days=rng.randint(10, 100))).isoformat()
            stats["expired"] += 1
        else:
            # expires 100-400 days AFTER the effective date -- comfortably current
            license_expiration_date = (effective + timedelta(days=rng.randint(100, 400))).isoformat()

        is_stale = rng.random() < STALE_PSV_FRACTION
        if is_stale:
            # checked 200-420 days BEFORE the effective date -- outside the lookback window
            psv_check_date = (effective - timedelta(days=rng.randint(200, 420))).isoformat()
            stats["stale_psv"] += 1
        else:
            # checked 1-150 days BEFORE the effective date -- inside the lookback window
            psv_check_date = (effective - timedelta(days=rng.randint(1, 150))).isoformat()

        has_adverse = rng.random() >= NO_ADVERSE_FRACTION
        finding = severity = None
        if has_adverse:
            stats["adverse_present"] += 1
            ambiguous = rng.random() < AMBIGUOUS_FRACTION
            if ambiguous:
                finding = _mild_adverse(rng)
                severity = "mild"
                stats["adverse_mild"] += 1
            else:
                finding = _severe_adverse(rng)
                severity = "severe"
                stats["adverse_severe"] += 1
        else:
            finding = _clean_finding(rng)
            stats["clean"] += 1

        rec_id = "CR-%04d" % i
        lines = [
            _underline("Provider"), name, "",
            _underline("NPI"), npi, "",
            _underline("Provider Type"), provider_type, "",
            _underline("License Number"), license_number, "",
            _underline("License Expiration Date"), license_expiration_date, "",
            _underline("Credentialing Effective Date"), credentialing_effective_date, "",
            _underline("PSV Check Date"), psv_check_date, "",
            _underline("PSV Source"), psv_source, "",
            _underline("PSV Finding"), finding, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": rec_id,
            "provider_name": name, "npi": npi, "license_number": license_number,
            "provider_type": provider_type,
            "license_expiration_date": license_expiration_date,
            "credentialing_effective_date": credentialing_effective_date,
            "psv_check_date": psv_check_date, "psv_source": psv_source,
            "psv_raw_finding": finding,
            "sanction_or_adverse_action_found": "yes" if has_adverse else "no",
        }
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    for rec_id, text, gold in rows:
        assert gold["license_expiration_date"] in text, rec_id
        assert gold["psv_check_date"] in text, rec_id
        assert gold["psv_raw_finding"] in text, rec_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_FILES)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for rec_id, text, _gold in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    print("files: %d   clean: %d   adverse: %d (mild: %d, severe: %d)"
          % (len(rows), stats["clean"], stats["adverse_present"], stats["adverse_mild"],
             stats["adverse_severe"]))
    print("expired licenses: %d   stale PSV (>%d days): %d"
          % (stats["expired"], PSV_LOOKBACK_DAYS, stats["stale_psv"]))
    print("internal consistency check: PASSED (every file's stated dates and PSV finding "
          "reconcile against its own document text)")


if __name__ == "__main__":
    main()
