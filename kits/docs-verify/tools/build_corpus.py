"""Turn the raw ClinicalTrials.gov pulls into the shipped corpus AND its labelled claim set.

YOU DO NOT NEED TO RUN THIS — both outputs are checked in. It is recorded because a claim about
how a dataset was built is worth nothing if the steps are not written down. Unlike UC001's
builder, this one shells out to nothing: it is pure standard library and reproduces byte-for-byte
from the same `data/_fetched/` pull.

    python -m tools.build_corpus

── WHY THE LABELS CANNOT DRIFT FROM THE TEXT ──────────────────────────────────────────────────
The failure mode for a claim-checking dataset is subtle: you write 90 claims by hand against 20
documents, then edit a document, and now some unknown number of your labels are wrong and nothing
tells you. UC006 solved the same problem for spans by rendering the document and reading the
labels out of ONE dict. This does the same thing one level up.

Every claim here is DERIVED from a structured field of the record — the same field the document
text is rendered from — so the text and the label come from a single source by construction:

  SUPPORTED     a template filled with the record's OWN value            ("Phase 3"  <- phases)
  CONTRADICTED  the same template filled with a DIFFERENT value          ("Phase 2"  <- perturbed)
  NOT_STATED    an assertion about something CTG protocol records do not carry at all

Nothing is typed against a finished document, so nothing can fall out of step with one.

── WHY `NOT_STATED` IS THE CLASS THIS KIT EXISTS FOR ──────────────────────────────────────────
A contradiction is easy: two values disagree and any careful reader finds it. The expensive
mistake in production is the claim that is plausible, on-topic, and simply absent — which is what
a hallucination looks like from the outside. If a grader collapses "not stated" into "not
supported" it can no longer tell a model that invented a fact from one that caught a real error,
and those need opposite responses. So the third class is first-class here, and the NOT_STATED
templates below are deliberately the kind of sentence a plausible summariser would produce:
publication status, funding arrangements, protocol amendments, site training, participant
compensation. None of them is recorded in a protocol section.

⚠︎ EVERY NOT_STATED CLAIM IS VERIFIED ABSENT, NOT ASSUMED ABSENT. `_verify()` fails the build if a
not-stated claim's trigger words turn up anywhere in the document it is asked about — otherwise a
registry change could quietly turn a not-stated label into a wrong one. It fails the same way if a
supported claim's own value is not literally present in its document.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "_fetched")
OUT = os.path.join(HERE, "data", "corpus")
CLAIMS = os.path.join(HERE, "data", "claims.jsonl")

N_DOCS = 20

PHASE_WORD = {"PHASE1": "Phase 1", "PHASE2": "Phase 2", "PHASE3": "Phase 3", "PHASE4": "Phase 4",
              "EARLY_PHASE1": "Early Phase 1", "PHASE1, PHASE2": "Phase 1/Phase 2",
              "PHASE2, PHASE3": "Phase 2/Phase 3", "NA": "Not Applicable"}
MASK_WORD = {"NONE": "open label, with no masking", "SINGLE": "single blind",
             "DOUBLE": "double blind", "TRIPLE": "triple blind", "QUADRUPLE": "quadruple blind"}
ALLOC_WORD = {"RANDOMIZED": "randomised", "NON_RANDOMIZED": "non-randomised", "NA": "not applicable"}
SEX_WORD = {"ALL": "all sexes", "FEMALE": "female participants only", "MALE": "male participants only"}


def _g(d, *path):
    x = d
    for p in path:
        if not isinstance(x, dict):
            return None
        x = x.get(p)
    return x


def render(st):
    """One record as a plain-text document. Section headings are the field names a reader would
    recognise, not the API's camelCase — the kit is meant to read like a document, not a dump."""
    ps = st.get("protocolSection", {})
    nct = _g(ps, "identificationModule", "nctId")
    L = []
    L.append("CLINICAL TRIAL RECORD")
    L.append("Registry identifier: %s" % nct)
    L.append("")
    L.append("Title: %s" % (_g(ps, "identificationModule", "briefTitle") or "—"))
    L.append("")
    conds = _g(ps, "conditionsModule", "conditions") or []
    L.append("Conditions studied: %s" % (", ".join(conds) if conds else "—"))
    spon = _g(ps, "sponsorCollaboratorsModule", "leadSponsor") or {}
    L.append("Lead sponsor: %s" % (spon.get("name") or "—"))
    L.append("Overall status: %s" % (_g(ps, "statusModule", "overallStatus") or "—"))
    sd = _g(ps, "statusModule", "startDateStruct") or {}
    L.append("Study start date: %s" % (sd.get("date") or "—"))
    L.append("")
    L.append("STUDY DESIGN")
    phases = _g(ps, "designModule", "phases") or []
    L.append("Phase: %s" % (PHASE_WORD.get(", ".join(phases), ", ".join(phases)) if phases else "—"))
    di = _g(ps, "designModule", "designInfo") or {}
    L.append("Allocation: %s" % (di.get("allocation") or "—"))
    L.append("Intervention model: %s" % (di.get("interventionModel") or "—"))
    L.append("Primary purpose: %s" % (di.get("primaryPurpose") or "—"))
    L.append("Masking: %s" % (_g(di, "maskingInfo", "masking") or "—"))
    en = _g(ps, "designModule", "enrollmentInfo") or {}
    L.append("Enrollment: %s [%s]" % (en.get("count", "—"), (en.get("type") or "—").capitalize()))
    L.append("")
    L.append("ELIGIBILITY")
    em = ps.get("eligibilityModule", {})
    L.append("Ages eligible for study: %s to %s"
             % (em.get("minimumAge") or "—", em.get("maximumAge") or "N/A"))
    L.append("Sexes eligible for study: %s" % (em.get("sex") or "—"))
    L.append("Accepts healthy volunteers: %s"
             % ("Yes" if em.get("healthyVolunteers") else "No"))
    L.append("")
    L.append("PRIMARY OUTCOME MEASURES")
    for o in (_g(ps, "outcomesModule", "primaryOutcomes") or [])[:3]:
        L.append("- %s [Time Frame: %s]" % (o.get("measure") or "—", o.get("timeFrame") or "—"))
    L.append("")
    L.append("BRIEF SUMMARY")
    summ = (_g(ps, "descriptionModule", "briefSummary") or "").strip()
    L.append(re.sub(r"\s+", " ", summ)[:1200] or "—")
    return "\n".join(L) + "\n"


# ── NOT_STATED templates. Each carries the words that would betray it if the registry DID record
# the thing — `_verify()` greps the document for them and fails the build on a hit.
NOT_STATED = [
    ("The results of this trial have been published in a peer-reviewed journal.",
     ["peer-reviewed", "peer reviewed", "published in", "journal"]),
    ("Participants were compensated for their travel costs.",
     ["compensat", "reimburse", "travel cost", "stipend"]),
    ("The study protocol was amended after enrolment began.",
     ["amend", "protocol was revised", "protocol change"]),
    ("Site staff completed a training programme before the first participant was enrolled.",
     ["training", "trained staff", "site staff"]),
    ("No serious adverse events were reported during the trial.",
     ["adverse event", "serious adverse", "safety event"]),
    ("An independent data monitoring committee reviewed the interim results.",
     ["monitoring committee", "data monitoring", "interim analys", "dsmb"]),
]


def _absent(needle, hay):
    """Is `needle` genuinely not in `hay`, on WORD BOUNDARIES rather than as a substring?

    Plain `in` is wrong for the perturbed values this file generates, and wrong in the direction
    that costs a real claim: "120" is a substring of "1200", so a contradiction asserting 120
    participants against a document that says 1200 read as "the document contains it" and the
    build refused a perfectly good claim. Boundaries fix that without weakening the check — the
    point is whether the document says this VALUE, not whether the characters occur somewhere.
    """
    return re.search(r"(?<![\w.])%s(?![\w.])" % re.escape(str(needle)), hay, re.I) is None


def claims_for(st, idx, doc_text):
    """Derive this record's claims. Deterministic: index-driven, never random."""
    ps = st.get("protocolSection", {})
    out = []

    def add(text, label, field, evidence=None):
        out.append({"text": text, "label": label, "field": field, "evidence": evidence})

    # ── EVERY FIELD PRODUCES BOTH CLASSES, and that is a measurement decision rather than a
    # stylistic one. The first build contradicted only `phase`, `enrollment` and `allocation` and
    # left the other five always-true, which is two separate defects: the set came out 76%
    # supported (a grader that answers "supported" to everything scores 76), and the falsehoods
    # were all concentrated in three field types, so a model could score well by learning "claims
    # about phase are suspicious" rather than by reading the document. Rotating on (idx + j)
    # spreads roughly a third of every field's claims into `contradicted`, evenly across the
    # corpus, and keeps the whole thing deterministic.
    em = ps.get("eligibilityModule", {})
    di = _g(ps, "designModule", "designInfo") or {}
    en = _g(ps, "designModule", "enrollmentInfo") or {}
    po = (_g(ps, "outcomesModule", "primaryOutcomes") or [])

    fields = []

    phases = _g(ps, "designModule", "phases") or []
    ph = ", ".join(phases)
    if ph and ph in PHASE_WORD and ph != "NA":
        word = PHASE_WORD[ph]
        others = [v for k, v in PHASE_WORD.items()
                  if v != word and k in ("PHASE1", "PHASE2", "PHASE3", "PHASE4")]
        fields.append(("phase", "This study is a %s trial.", word, others[idx % len(others)], word))

    if isinstance(en.get("count"), int):
        n = en["count"]
        # The offset is SEARCHED, not assumed. +10 collided on the first balanced build: one
        # record enrolled 110 and its summary mentions 1200, and `"120" in text` is true of
        # "1200". _absent() matches on word boundaries so that particular false alarm is gone,
        # but a real collision is still possible, so the perturbation walks until it finds a
        # count the document genuinely does not contain.
        wrong_n = next((n + d for d in (10, 20, 30, 40, 50, 60, 70)
                        if _absent(str(n + d), doc_text)), n + 137)
        fields.append(("enrollment", "Enrolment was %s participants.",
                       str(n), str(wrong_n), str(n)))

    alloc = di.get("allocation")
    if alloc in ALLOC_WORD and alloc != "NA":
        truth = ALLOC_WORD[alloc]
        wrong = "non-randomised" if truth == "randomised" else "randomised"
        fields.append(("allocation", "Participants were assigned to groups by a %s design.",
                       truth, wrong, alloc))

    mask = _g(di, "maskingInfo", "masking")
    if mask in MASK_WORD:
        wrong = MASK_WORD["DOUBLE"] if mask != "DOUBLE" else MASK_WORD["NONE"]
        fields.append(("masking", "The trial was run %s.", MASK_WORD[mask], wrong, mask))

    lo, hi = em.get("minimumAge"), em.get("maximumAge")
    if lo and hi:
        # Shift the lower bound by a decade — still a plausible eligibility band, definitely wrong.
        m = re.match(r"(\d+)(.*)", str(lo))
        wrong_lo = ("%d%s" % (int(m.group(1)) + 10, m.group(2))) if m else "30 Years"
        fields.append(("age", "Participants aged %s were eligible.",
                       "%s to %s" % (lo, hi), "%s to %s" % (wrong_lo, hi), lo))

    if em.get("sex") in SEX_WORD:
        wrong = SEX_WORD["FEMALE"] if em["sex"] != "FEMALE" else SEX_WORD["MALE"]
        fields.append(("sex", "The study was open to %s.", SEX_WORD[em["sex"]], wrong, em["sex"]))

    if po and po[0].get("timeFrame"):
        tf = re.sub(r"\s+", " ", po[0]["timeFrame"]).strip().rstrip(".")
        if len(tf) <= 60:
            fields.append(("outcome", "The primary outcome was measured over %s.",
                           tf, "a single visit at week 2", tf))

    spon = _g(ps, "sponsorCollaboratorsModule", "leadSponsor", "name")
    if spon:
        fields.append(("sponsor", "The trial's lead sponsor was %s.",
                       spon, "the World Health Organization", spon))

    for j, (name, tmpl, truth, wrong, evid) in enumerate(fields):
        if (idx + j) % 3 == 0:
            add(tmpl % wrong, "contradicted", name, evid)
            out[-1]["_wrong"] = wrong
        else:
            add(tmpl % truth, "supported", name, evid)

    # ── exactly one NOT_STATED per document. Rotating start so the six templates spread evenly,
    # then FIRST FIT: the first template whose trigger words are genuinely absent from this
    # document wins. Taking the rotation blindly shipped a wrong label on the first build — one
    # record's brief summary discusses adverse events, which makes "no serious adverse events
    # were reported" a claim the document does speak to. Deterministic either way; this version
    # is also correct.
    low = doc_text.lower()
    taken = 0
    for k in range(len(NOT_STATED)):
        text, triggers = NOT_STATED[(idx + k) % len(NOT_STATED)]
        if any(t in low for t in triggers):
            continue
        add(text, "not_stated", "absent", None)
        out[-1]["_triggers"] = triggers
        taken += 1
        if taken == 2:
            break
    if taken < 2:
        raise SystemExit("%s: fewer than two NOT_STATED templates survive this document; it needs "
                         "new templates rather than a relaxed check"
                         % _g(ps, "identificationModule", "nctId"))
    return out


def _verify(doc_text, claims, nct):
    """Fail loudly rather than ship a wrong label. Both directions are checked."""
    low = doc_text.lower()
    for c in claims:
        if c["label"] == "supported" and c.get("evidence"):
            if str(c["evidence"]).lower() not in low:
                raise SystemExit(
                    "%s: SUPPORTED claim's own value %r does not appear in the document it "
                    "claims to be supported by. The renderer and the claim builder have drifted."
                    % (nct, c["evidence"]))
        if c["label"] == "contradicted":
            # BOTH halves, because a contradiction is a relationship and not a value. The true
            # value has to be in the document (or there is nothing to contradict, and the honest
            # label would be not_stated), and the asserted value must NOT be (or the document
            # supports it after all and the label is simply wrong).
            if c.get("evidence") and str(c["evidence"]).lower() not in low:
                raise SystemExit(
                    "%s: CONTRADICTED claim cites a true value %r the document does not contain — "
                    "with nothing to contradict, this is a not_stated claim wearing the wrong "
                    "label." % (nct, c["evidence"]))
            w = str(c.get("_wrong", ""))
            if w and not _absent(w, doc_text):
                raise SystemExit(
                    "%s: CONTRADICTED claim asserts %r and the document CONTAINS that string, so "
                    "the document supports it. The perturbation collided with the real text."
                    % (nct, c["_wrong"]))
        if c["label"] == "not_stated":
            for t in c.get("_triggers", []):
                if t in low:
                    raise SystemExit(
                        "%s: NOT_STATED claim %r is betrayed by the word %r in the document — "
                        "the registry now records this and the label is wrong."
                        % (nct, c["text"][:50], t))


def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(f for f in os.listdir(RAW) if f.endswith(".json"))[:N_DOCS]
    rows, n_claims = [], 0
    for idx, fn in enumerate(files):
        st = json.load(open(os.path.join(RAW, fn), encoding="utf-8"))
        nct = _g(st, "protocolSection", "identificationModule", "nctId") or fn[:-5]
        text = render(st)
        with open(os.path.join(OUT, nct + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(text)
        cl = claims_for(st, idx, text)
        _verify(text, cl, nct)
        for i, c in enumerate(cl):
            c.pop("_triggers", None); c.pop("_wrong", None)
            c["id"] = "%s-c%02d" % (nct, i + 1)
        rows.append({"doc": nct + ".txt", "claims": cl})
        n_claims += len(cl)
    with open(CLAIMS, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    dist = {}
    for r in rows:
        for c in r["claims"]:
            dist[c["label"]] = dist.get(c["label"], 0) + 1
    print("corpus : %d documents -> data/corpus/" % len(rows))
    print("claims : %d -> data/claims.jsonl" % n_claims)
    for k in sorted(dist):
        print("   %-14s %d" % (k, dist[k]))


if __name__ == "__main__":
    main()
