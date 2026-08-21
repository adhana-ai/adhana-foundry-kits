#!/usr/bin/env python3
"""Generate synthetic adverse-event case reports and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one case per file) and data/gold.jsonl, byte-identical on every run.
Every case identifier, drug name and narrative here is invented -- nothing is fetched and nothing
is licensed from anybody, so the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ THERE IS NO PATIENT AND NO REPORTER IN THIS CORPUS, BY CONSTRUCTION. No names, no dates of
birth, no exact ages, no free-text identifiers -- age arrives as a bucketed range and the reporter
arrives as one of four role words. A real adverse-event narrative is among the most identifying
text a company holds; a synthetic one has no reason to imitate that part of it.

⚑ GOLD IS DERIVED FROM THE GENERATOR'S OWN DECISION, NEVER RE-READ OFF THE SURFACE WORDS. The
seriousness label is the criterion branch that produced the narrative -- not a scorer's reading of
how alarming the narrative sounds, which is the exact shortcut this kit exists to measure.

⚑ THE PLANTED AMBIGUITY: "serious" is a regulatory classification and "severe" is a colloquial
description of how an event felt, and they are not the same test. `AMBIGUOUS_FRACTION` of these
records carry a severity word from the WRONG register on purpose -- a "mild"-worded rash that led
to a three-day admission (serious), a "severe"-worded headache that resolved at home with no
medical attention (not serious). A classifier that reads the severity word instead of the outcome
gets the other 60% right and fails here, which is the whole demonstration.

⚑ WHY MOST SERIOUS RECORDS ARE NOT HOSPITALISATIONS. Hospitalisation and death are the two
seriousness criteria this record layout states in a structured field of their own, so a corpus
weighted towards them would be solvable by reading two enums and would test nothing. Four of the
six criteria -- life-threatening, persistent disability, congenital anomaly, and an event
medically important enough to need an intervention to prevent one of the others -- are stated only
in the narrative prose, and 60% of this corpus's serious records are built from those four.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260821
N_RECORDS = 55

# 40% of records carry a severity word from the wrong register on purpose. Of the remainder, some
# carry no severity word at all -- a real narrative often does not reach for one, and a field that
# is legitimately null is the only way to test that the model returns null instead of guessing.
AMBIGUOUS_FRACTION = 0.40
NO_WORD_FRACTION = 0.18          # applied to the non-ambiguous remainder only
SERIOUS_FRACTION = 0.55

# ⚑ THE KIT'S OWN ROUTING RULE, NOT A REAL PROGRAM'S REPORTING CLOCK. See README/SOURCES.md.
CAUSALITY_TRIGGERS = ("related", "possibly-related")

# Invented, INN-style. Deliberately not a real trade name or a real generic stem in current use --
# a synthetic corpus that names a real product implies a real product's safety record.
DRUGS = ["Velmerix", "Cantrivane", "Orbadanil", "Suvexatine", "Palmirozan",
         "Ivoraxine", "Mycolarin", "Nabrexil", "Zorvatide", "Kelvaprine"]

AGE_RANGES = ["0-17", "18-29", "30-44", "45-54", "55-64", "65-74", "75+"]
REPORTER_TYPES = ["physician", "pharmacist", "consumer", "other-healthcare-professional"]

EVENTS = ["headache with photophobia", "rash on both forearms", "nausea and vomiting",
          "dizziness on standing", "swelling of the lips and tongue", "shortness of breath",
          "palpitations", "joint pain in both knees", "ringing in the ears", "abdominal pain",
          "blurred vision", "confusion and disorientation", "muscle weakness in both legs",
          "itching of the trunk and back"]

# ⚠︎ EVERY NARRATIVE BELOW IS EVENT-AGNOSTIC, AND THE FIRST DRAFT WAS NOT. It named specific
# clinical findings -- a platelet transfusion, a closing airway -- which the generator then paired
# at random with an unrelated Event Description, producing records like "mild itching of the trunk
# and back" whose narrative was about a falling platelet count. The label was still correct and
# every assertion still passed, so nothing caught it; it was found by reading the output. A corpus
# that reads as incoherent to a person invites the reader to distrust the labels too, and it gives
# a model a reason to answer the wrong question. Narratives now describe "the reaction" and let
# the Event Description say what the reaction was.
#
# Congenital anomaly is the one criterion that cannot be event-agnostic -- it is an outcome in an
# infant after exposure in pregnancy, so its records draw the MATERNAL event from a narrower pool.
PREGNANCY_EVENTS = ["nausea and vomiting", "headache with photophobia", "dizziness on standing",
                    "rash on both forearms"]
# ...and the same record cannot be filed under an age band that makes the pregnancy implausible.
# The first pass paired a first-trimester exposure with the "55-64" band; found the same way, by
# reading the output rather than by any assertion.
PREGNANCY_AGE_RANGES = ["18-29", "30-44"]

# ⚠︎ THE ONLY PLACE ANY REGISTER WORD MAY APPEAR IN A DOCUMENT. _verify() asserts it -- a stray
# "severe" in a narrative would hand the keyword floor a signal the corpus never meant to give it,
# and would do so silently.
REGISTER_SEVERE = "severe"
REGISTER_MILD = ("mild", "moderate")
# "serious" and its relatives are the ANSWER'S vocabulary. A document that uses the word has
# leaked the label into the input; _verify() refuses to write a corpus that does.
BANNED_IN_DOCS = ("serious", "seriously", "seriousness", "severely")


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


# ---------------------------------------------------------------------------------------------
# The six seriousness criteria. Each returns (narrative, hospitalization, event_outcome).
# The criterion the generator picks IS the gold label's justification; nothing re-reads the prose.
# ---------------------------------------------------------------------------------------------

def _crit_death(rng):
    return (rng.choice([
        "The patient was found unresponsive at home on the fourth day of treatment and could not "
        "be revived. The reporting clinician records the outcome as fatal and has forwarded a "
        "copy of the death certificate with this report.",
        "The patient collapsed at home two days after the dose was increased and was declared "
        "dead at the scene. The reporting clinician has recorded the outcome as fatal.",
    ]), "no", "fatal")


def _crit_life_threatening(rng):
    return (rng.choice([
        "Within twenty minutes of the dose the patient deteriorated to the point that the "
        "treating clinician recorded the episode as immediately life-threatening and called for "
        "resuscitation support. The patient was stabilised in the treatment room over the "
        "following hour. No admission was required.",
        "The reaction escalated quickly and the attending clinician recorded it as "
        "life-threatening at the time, with resuscitation equipment brought to the bedside. The "
        "patient was stabilised in the clinic and went home the same afternoon.",
    ]), "no", "recovered")


def _crit_hospitalization(rng):
    return (rng.choice([
        "The patient attended the emergency department and was admitted for three days of "
        "observation and intravenous fluids before being discharged home.",
        "The patient was admitted overnight for monitoring and discharged the following day once "
        "the reaction had settled.",
        "The patient was already an inpatient for an unrelated procedure and the admission was "
        "extended by four days so that the reaction could be monitored.",
    ]), "yes", "recovered")


def _crit_disability(rng):
    return (rng.choice([
        "The reaction has not resolved. At the ninety-day follow-up the reporting clinician "
        "records a persistent impairment that continues to limit the patient's day-to-day "
        "activity, with no expectation of further recovery. The patient was not admitted at any "
        "point.",
        "Three months after onset the patient remains unable to return to work because of the "
        "reaction. The reporting clinician records the incapacity as persistent and significant. "
        "No admission was required at any stage.",
    ]), "no", "not-recovered")


def _crit_congenital(rng):
    return (rng.choice([
        "The patient was exposed to the drug throughout the first trimester and reported the "
        "reaction during that period. The infant was later delivered at term with a cleft palate, "
        "which the reporting clinician has recorded as a congenital anomaly. Neither mother nor "
        "infant required admission for the anomaly itself.",
        "Exposure continued into the second trimester, with the reaction reported partway "
        "through. The infant was born with a limb reduction defect, recorded by the reporting "
        "clinician as a congenital anomaly. No admission followed for the mother.",
    ]), "no", "recovering")


def _crit_medically_important(rng):
    return (rng.choice([
        "The reaction did not require admission, but the treating clinician judged it important "
        "enough to give an intravenous intervention in the day unit specifically to stop it "
        "progressing further, and observed the patient for four hours before discharge.",
        "The patient was seen urgently in the day unit, where the treating clinician intervened "
        "to prevent the reaction progressing to organ involvement. No admission followed and the "
        "patient was discharged the same day.",
    ]), "no", "recovering")


# ⚑ UNIFORM ACROSS THE SIX CRITERIA, WHICH IS A COVERAGE CHOICE AND NOT A PREVALENCE CLAIM. A
# real safety database is dominated by hospitalisation; sampling that way here would leave a
# criterion represented by one or two records, where a model missing it entirely would be
# invisible in the score. An earlier weighting did exactly that -- congenital anomaly landed on a
# single record. Every criterion now gets roughly a fifth of the serious set, so a systematic miss
# on any one of them shows up. It also means hospitalisation and death -- the only two criteria
# this record layout states in a structured field of their own -- are together a THIRD of the
# serious records; the other two thirds can only be found by reading the narrative.
SERIOUS_CRITERIA = [
    ("death", _crit_death),
    ("life-threatening", _crit_life_threatening),
    ("hospitalization", _crit_hospitalization),
    ("persistent-disability", _crit_disability),
    ("congenital-anomaly", _crit_congenital),
    ("other-medically-important", _crit_medically_important),
]


def _not_serious(rng):
    """No criterion is met. Outcome may still be unflattering -- 'not-recovered' is not the test."""
    return rng.choice([
        ("The patient managed the reaction at home with rest and fluids. No medical attention was "
         "sought and the symptoms had settled by the following morning.", "no", "recovered"),
        ("The patient telephoned the pharmacy for advice, stopped the drug, and the reaction "
         "faded over four days without treatment. No clinic or emergency visit took place.",
         "no", "recovered"),
        ("The reporting clinician saw the patient at a routine appointment, advised symptomatic "
         "treatment only, and recorded that no further action was needed.", "no", "recovered"),
        ("Symptoms were still present at the time of reporting but the patient continues normal "
         "daily activity. Nothing beyond stopping the drug has been done and no admission or "
         "emergency visit has taken place.", "no", "recovering"),
        ("The reaction has persisted at a low level for six weeks. The patient has not sought "
         "care beyond the initial telephone advice and remains fully active; no admission, no "
         "emergency visit and no treatment have been required.", "no", "not-recovered"),
    ])


def _severity_word(rng, is_serious, ambiguous, no_word):
    """The colloquial word the report itself reaches for -- the decoy this kit is built around."""
    if no_word:
        return None
    if ambiguous:
        # written against type on purpose
        return rng.choice(REGISTER_MILD) if is_serious else REGISTER_SEVERE
    return REGISTER_SEVERE if is_serious else rng.choice(REGISTER_MILD)


def build_all(rng, n=N_RECORDS):
    stats = {"serious": 0, "not_serious": 0, "ambiguous": 0, "no_word": 0,
             "criteria": {}, "flagged": 0}
    out = []
    for i in range(1, n + 1):
        is_serious = rng.random() < SERIOUS_FRACTION
        ambiguous = rng.random() < AMBIGUOUS_FRACTION
        no_word = (not ambiguous) and (rng.random() < NO_WORD_FRACTION)

        if is_serious:
            crit_name, crit = rng.choice(SERIOUS_CRITERIA)
            narrative, hosp, outcome = crit(rng)
            stats["serious"] += 1
            stats["criteria"][crit_name] = stats["criteria"].get(crit_name, 0) + 1
        else:
            crit_name = "none-met"
            narrative, hosp, outcome = _not_serious(rng)
            stats["not_serious"] += 1
            stats["criteria"]["none-met"] = stats["criteria"].get("none-met", 0) + 1

        if ambiguous:
            stats["ambiguous"] += 1
        if no_word:
            stats["no_word"] += 1

        word = _severity_word(rng, is_serious, ambiguous, no_word)
        # Congenital anomaly is an infant outcome after exposure in pregnancy, so its maternal
        # event comes from the narrower pool -- see the note above PREGNANCY_EVENTS.
        event = rng.choice(PREGNANCY_EVENTS if crit_name == "congenital-anomaly" else EVENTS)
        event_description = ("%s %s" % (word, event)) if word else event

        causality = rng.choices(
            ["related", "possibly-related", "unrelated", "not-assessed"],
            weights=[30, 35, 20, 15])[0]
        reporter = rng.choice(REPORTER_TYPES)
        age_range = rng.choice(
            PREGNANCY_AGE_RANGES if crit_name == "congenital-anomaly" else AGE_RANGES)
        drug = rng.choice(DRUGS)

        rec_id = "AE-%04d" % i
        case_id = "AE-2026-%04d" % i

        lines = [
            _underline("Case ID"), case_id, "",
            _underline("Patient Age Range"), age_range, "",
            _underline("Suspect Drug"), drug, "",
            _underline("Event Description"), event_description, "",
            _underline("Hospitalization"), hosp, "",
            _underline("Event Outcome"), outcome, "",
            _underline("Reporter Causality Assessment"), causality, "",
            _underline("Reporter Type"), reporter, "",
            _underline("Case Narrative"), narrative, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": rec_id,
            "case_id": case_id,
            "patient_age_range": age_range,
            "suspect_drug": drug,
            "event_description": event_description,
            "narrative_severity_word": word,
            "hospitalization": hosp,
            "event_outcome": outcome,
            "causality_assessment": causality,
            "reporter_type": reporter,
            "is_serious": "yes" if is_serious else "no",
            # NOT a scored field -- carried so SOURCES.md and the honesty fields can say which
            # criterion each serious record was built from without re-reading the prose.
            "_criterion": crit_name,
            "_register": "confusable" if ambiguous else ("no-word" if no_word else "matching"),
        }
        if is_serious and causality in CAUSALITY_TRIGGERS:
            stats["flagged"] += 1
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    """Every gold value is stated verbatim in its own document, and no register word leaks.

    The second half is the one that matters. The keyword floor in evals/baseline.py reads the
    document for a severity word; if a narrative happens to contain "severe" for an unrelated
    reason the floor gets a signal this corpus never meant to plant, the baseline's measured gap
    shrinks, and nothing anywhere says why.
    """
    for rec_id, text, gold in rows:
        low = text.lower()
        for key in ("case_id", "patient_age_range", "suspect_drug", "event_description",
                    "hospitalization", "event_outcome", "causality_assessment", "reporter_type"):
            assert gold[key] in text, "%s: %s=%r not stated verbatim" % (rec_id, key, gold[key])

        word = gold["narrative_severity_word"]
        if word is None:
            for w in (REGISTER_SEVERE,) + REGISTER_MILD:
                assert w not in low, "%s: register word %r leaked into a no-word record" % (rec_id, w)
        else:
            assert word in text, "%s: severity word %r not in the document" % (rec_id, word)
            for w in (REGISTER_SEVERE,) + REGISTER_MILD:
                if w == word:
                    assert low.count(w) == 1, "%s: %r appears %d times, expected once" % (
                        rec_id, w, low.count(w))
                else:
                    assert w not in low, "%s: unintended register word %r" % (rec_id, w)

        for w in BANNED_IN_DOCS:
            assert w not in low, "%s: the label's own vocabulary %r leaked into the input" % (rec_id, w)

        # ⚑ ASSERTED BECAUSE IT WAS MEASURED FAILING, NOT BECAUSE IT SOUNDED LIKE A RULE. The
        # first two generated corpora paired first-trimester exposure with an unrelated event and
        # with the "55-64" age band. Both labels were still correct and every other assertion
        # passed, which is exactly why this one is here.
        if gold["_criterion"] == "congenital-anomaly":
            assert gold["patient_age_range"] in PREGNANCY_AGE_RANGES, \
                "%s: congenital-anomaly record filed under age band %r" % (
                    rec_id, gold["patient_age_range"])
            assert any(e in gold["event_description"] for e in PREGNANCY_EVENTS), \
                "%s: congenital-anomaly record describes %r" % (
                    rec_id, gold["event_description"])


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
    for rec_id, text, _gold in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold in rows:
            fh.write(json.dumps(gold) + "\n")

    n = len(rows)
    print("records: %d   serious: %d   not serious: %d"
          % (n, stats["serious"], stats["not_serious"]))
    print("%d (%.0f%%) written in the confusable register (severity word against type);   "
          "%d (%.0f%%) use no severity word at all"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / n,
             stats["no_word"], 100.0 * stats["no_word"] / n))
    print("seriousness criteria met: %s"
          % ", ".join("%s=%d" % kv for kv in sorted(stats["criteria"].items())))
    print("should be flagged (serious AND causality in %s): %d"
          % (", ".join(CAUSALITY_TRIGGERS), stats["flagged"]))
    print("internal consistency check: PASSED (every gold value is stated verbatim in its own "
          "document; no register word and no label vocabulary leaked into any input)")


if __name__ == "__main__":
    main()
