"""Turn the raw ClinicalTrials.gov pulls into the shipped corpus AND its gold verdicts.

YOU DO NOT NEED TO RUN THIS — both outputs are checked in. It is recorded because a claim about
how a dataset was built is worth nothing if the steps are not written down. Pure standard library;
reproduces byte-for-byte from the same `data/_fetched/` pull.

    python -m tools.build_corpus

── WHY THE GOLD VERDICTS CANNOT DRIFT FROM THE DOCUMENTS ──────────────────────────────────────
Same discipline as UC006 (spans) and UC007 (claims), one level up again. Nothing here is
hand-labelled. Every verdict is computed from the STRUCTURED record — the same structured record
the document text is rendered from — so the text and the label come from a single source by
construction. Edit the renderer and the labels move with it; there is no second place to forget.

`_verify()` then checks the two directions that would otherwise fail silently:
  · a MET or BREACHED verdict must quote a line that literally appears in its document;
  · a NEVER-ADDRESSED verdict must quote nothing, and the element's own heading must be absent.

── THE FOUR-STATE LOGIC, AND WHY IT IS NOT THREE ──────────────────────────────────────────────
The panel shows three verdicts. The label set carries a fourth, `not_applicable`, which never
reaches the panel because a rule that does not bind this document is not a rule this document can
pass or fail. Scoring a checker against inapplicable rules is how a kit invents accuracy: 41 rules
where 8 do not apply is a 20% free ride for a model that stays silent.

  met              the element is present, and the line carrying it is quoted
  breached         the element is ADDRESSED AND DEFICIENT — a statement exists and fails the
                   requirement. Grounded in the regulation's own conditional language, never in a
                   house style rule (see the three below)
  never_addressed  the document is silent. No line can be quoted, so the quote must be empty
  not_applicable   the rule's own condition excludes this document — dropped before scoring

── WHERE `breached` COMES FROM. THREE RULES, EACH FROM THE REG'S OWN WORDS ─────────────────────
This is the load-bearing part of the design, so each one cites the sentence it rests on:

  Why Study Stopped   §11.10(b): "for a clinical trial that is suspended or terminated or withdrawn
                      prior to its planned completion … a brief explanation of the reason(s)".
                      On a TERMINATED/WITHDRAWN/SUSPENDED record, absence is a BREACH. On any other
                      status the rule does not apply at all — which is precisely what filtering a
                      corpus to COMPLETED destroys, and why this kit does not reuse UC007's.
  Enrollment          §11.10(b): "Once the trial has reached the primary completion date, the
                      responsible party must update the Enrollment data element to reflect the
                      actual number". An ESTIMATED count on a record past its primary completion
                      date is a breach; the same count before that date is fine.
  Responsible Party   §11.28(a)(2)(iii)(B) names the element "Responsible Party, BY OFFICIAL
                      TITLE", and §11.10 defines it as "(2) If the responsible party is an
                      individual, the official title and primary organizational affiliation".
                      A record naming an individual investigator with no official title has
                      addressed the element and failed its stated form.

Anything I could not ground in the regulation is left as a plain present/absent rule. A fourth
candidate — "primary outcome stated without a time frame" — was DROPPED for exactly that reason:
the time frame is required by the ClinicalTrials.gov data dictionary, not by Part 11, and a kit
that quietly promotes a house rule to a federal one is lying about what it checks.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "_fetched")
OUT = os.path.join(HERE, "data", "corpus")
RULEBOOK = os.path.join(HERE, "data", "rulebook.json")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

PER_STATUS = 5          # 6 statuses x 5 = 30 documents
STOPPED = ("TERMINATED", "WITHDRAWN", "SUSPENDED")

MET, BREACH, NEVER, NA = "met", "breached", "never_addressed", "not_applicable"


def g(d, *path):
    x = d
    for p in path:
        if not isinstance(x, dict):
            return None
        x = x.get(p)
    return x


def unescape(v):
    """Undo the registry's markdown escaping in free-text fields.

    Eligibility criteria come back as "FEVI \\> 50% and \\< 90%". Those backslashes are an
    artefact of how ClinicalTrials.gov stores prose, not part of the document, and leaving them in
    puts characters in a quoted evidence line that no reader would recognise as the source text.
    """
    if not isinstance(v, str):
        return v
    return re.sub(r"\\([<>*_\[\]#`])", r"\1", v)


# ── The rendered document. ONE RULE GOVERNS IT: render only what the record HAS.
# A renderer that prints "Official Title: —" for a missing title would make every rule trivially
# "addressed", collapse never-addressed into breached, and quietly destroy the distinction the
# whole kit exists to draw. Absent field -> absent line.
def render(st):
    ps = st.get("protocolSection", {})
    idm = ps.get("identificationModule", {})
    stm = ps.get("statusModule", {})
    dsm = ps.get("designModule", {})
    di = dsm.get("designInfo") or {}
    em = ps.get("eligibilityModule", {})
    ovm = ps.get("oversightModule", {})
    scm = ps.get("sponsorCollaboratorsModule", {})
    clm = ps.get("contactsLocationsModule", {})
    L = []

    def line(label, value):
        if value not in (None, "", [], {}):
            L.append("%s: %s" % (label, unescape(value)))

    def close_section():
        """Drop the open heading if nothing was written under it, plus any trailing blanks.

        "Render only what the record has" has to apply to headings too. A record with no outcomes
        emitted a bare "OUTCOME MEASURES" heading with nothing under it, and a heading with no
        content is exactly the shape that makes a checker say the element was addressed — it would
        manufacture false MET verdicts out of pure layout, on the rule a reader is least able to
        check by eye.

        This owns the blank-line bookkeeping too. The first version left that to the callers and
        then tried to detect an empty section by looking at L[-1] — which is a blank line, never
        the heading, so it never fired and the empty heading shipped anyway.
        """
        while L and L[-1] == "":
            L.pop()
        if L and L[-1] == open_head[0]:
            L.pop()
        open_head[0] = None

    def section(name):
        close_section()
        if L:
            L.append("")
        L.append(name)
        open_head[0] = name

    open_head = [None]

    L.append("CLINICAL TRIAL REGISTRATION RECORD")
    line("Registry identifier", idm.get("nctId"))
    section("IDENTIFICATION")
    line("Brief Title", idm.get("briefTitle"))
    line("Official Title", idm.get("officialTitle"))
    line("Unique Protocol Identification Number", g(idm, "orgStudyIdInfo", "id"))
    sec = [s.get("id") for s in (idm.get("secondaryIdInfos") or []) if s.get("id")]
    line("Secondary ID", "; ".join(sec) if sec else None)
    ind = [s.get("id") for s in (idm.get("secondaryIdInfos") or [])
           if s.get("type") == "INDIDE" and s.get("id")]
    line("U.S. Food and Drug Administration IND or IDE Number", "; ".join(ind) if ind else None)
    section("DESCRIPTION")
    summ = re.sub(r"\s+", " ", (g(ps, "descriptionModule", "briefSummary") or "")).strip()
    line("Brief Summary", summ[:1200] or None)
    conds = ps.get("conditionsModule", {}).get("conditions") or []
    line("Primary Disease or Condition Being Studied in the Trial", ", ".join(conds) or None)
    section("STUDY DESIGN")
    line("Study Type", dsm.get("studyType"))
    phases = dsm.get("phases") or []
    line("Study Phase", ", ".join(phases) or None)
    line("Primary Purpose", di.get("primaryPurpose"))
    design_bits = [x for x in (di.get("allocation"), di.get("interventionModel"),
                               g(di, "maskingInfo", "masking")) if x]
    line("Study Design", "; ".join(design_bits) or None)
    en = dsm.get("enrollmentInfo") or {}
    if en.get("count") is not None:
        # The TYPE is rendered beside the count when the registry carries one, because the
        # Enrollment rule turns on exactly that word. Rendering the count alone would hide the
        # very deficiency the gold label records.
        line("Enrollment", "%s%s" % (en["count"],
                                     " [%s]" % en["type"].capitalize() if en.get("type") else ""))
    section("INTERVENTIONS")
    ivs = g(ps, "armsInterventionsModule", "interventions") or []
    for iv in ivs:
        line("Intervention Name", iv.get("name"))
        line("Intervention Type", iv.get("type"))
        line("Intervention Description",
             re.sub(r"\s+", " ", iv.get("description") or "").strip()[:400] or None)
        others = [o for o in (iv.get("otherNames") or []) if o]
        line("Other Intervention Name", "; ".join(others) if others else None)
    section("OUTCOME MEASURES")
    for o in (g(ps, "outcomesModule", "primaryOutcomes") or [])[:4]:
        line("Primary Outcome Measure Information",
             "%s%s" % (o.get("measure") or "",
                       " [Time Frame: %s]" % o["timeFrame"] if o.get("timeFrame") else ""))
    for o in (g(ps, "outcomesModule", "secondaryOutcomes") or [])[:4]:
        line("Secondary Outcome Measure Information",
             "%s%s" % (o.get("measure") or "",
                       " [Time Frame: %s]" % o["timeFrame"] if o.get("timeFrame") else ""))
    section("ELIGIBILITY AND RECRUITMENT")
    crit = re.sub(r"\s+", " ", (em.get("eligibilityCriteria") or "")).strip()
    line("Eligibility Criteria", crit[:900] or None)
    line("Sex/Gender", em.get("sex"))
    ages = " to ".join(x for x in (em.get("minimumAge"), em.get("maximumAge")) if x)
    line("Age Limits", ages or None)
    if em.get("healthyVolunteers") is not None:
        line("Accepts Healthy Volunteers", "Yes" if em["healthyVolunteers"] else "No")
    line("Overall Recruitment Status", stm.get("overallStatus"))
    line("Why Study Stopped", (stm.get("whyStopped") or "").strip() or None)
    section("DATES")
    line("Study Start Date", g(stm, "startDateStruct", "date"))
    line("Primary Completion Date", g(stm, "primaryCompletionDateStruct", "date"))
    line("Study Completion Date", g(stm, "completionDateStruct", "date"))
    line("Record Verification Date", stm.get("statusVerifiedDate"))
    section("REGULATORY")
    for label, key in (("Studies a U.S. FDA-regulated Drug Product", "isFdaRegulatedDrug"),
                       ("Studies a U.S. FDA-regulated Device Product", "isFdaRegulatedDevice"),
                       ("Device Product Not Approved or Cleared by U.S. FDA", "isUnapprovedDevice"),
                       ("Product Manufactured in and Exported from the U.S.", "isUsExport")):
        if ovm.get(key) is not None:
            line(label, "Yes" if ovm[key] else "No")
    if g(stm, "expandedAccessInfo", "hasExpandedAccess") is not None:
        line("Availability of Expanded Access",
             "Yes" if stm["expandedAccessInfo"]["hasExpandedAccess"] else "No")
    section("SPONSOR, RESPONSIBLE PARTY AND SITES")
    line("Name of the Sponsor", g(scm, "leadSponsor", "name"))
    rp = scm.get("responsibleParty") or {}
    if rp.get("type"):
        who = rp.get("investigatorFullName") or ""
        title = rp.get("investigatorTitle") or ""
        val = rp["type"].replace("_", " ").title()
        if who:
            val += " — %s" % who
        if title:
            val += ", %s" % title
        line("Responsible Party", val)
    cc = clm.get("centralContacts") or []
    if cc:
        c = cc[0]
        line("Responsible Party Contact Information",
             ", ".join(x for x in (c.get("name"), c.get("phone"), c.get("email")) if x) or None)
    for lo in (clm.get("locations") or [])[:LOC_LIMIT]:
        line("Facility Information", loc_value(lo))
    close_section()
    return "\n".join(L).rstrip() + "\n"


LOC_LIMIT = 6


def loc_value(lo):
    """The rendered value of one location line, or None if the record says nothing about it.

    ONE definition, used by the renderer AND by the evidence picker. When a breach has to quote a
    specific location — the one missing its facility name — rebuilding that string a second time
    at the quoting site is how a quote drifts out of the document it claims to come from.
    """
    bits = [x for x in (lo.get("facility"), lo.get("city"), lo.get("country")) if x]
    if not bits:
        return None
    return ", ".join(bits) + (" [Individual Site Status: %s]" % lo["status"]
                              if lo.get("status") else "")


def rendered_locations(clm):
    """The locations that actually appear in the document — the only ones a rule can speak about."""
    return [lo for lo in (clm.get("locations") or [])[:LOC_LIMIT] if loc_value(lo)]


# ── THE PROBES. Keyed on the ELEMENT NAME from the rulebook, not on R-nn.
# Rule ids are positional and would silently re-point if the regulation gained an element; element
# names are the vocabulary the part defines once and reuses. main() asserts every rule has a probe
# and fails loudly otherwise, so a change to the eCFR becomes a red build rather than a blind spot.
def _pres(v):
    return MET if v not in (None, "", [], {}) else NEVER


def probe(element, ps, doc):
    idm = ps.get("identificationModule", {})
    stm = ps.get("statusModule", {})
    dsm = ps.get("designModule", {})
    di = dsm.get("designInfo") or {}
    em = ps.get("eligibilityModule", {})
    ovm = ps.get("oversightModule", {})
    scm = ps.get("sponsorCollaboratorsModule", {})
    clm = ps.get("contactsLocationsModule", {})
    ivs = g(ps, "armsInterventionsModule", "interventions") or []
    status = stm.get("overallStatus")

    E = element

    if E == "Brief Title":
        return _pres(idm.get("briefTitle"))
    if E == "Official Title":
        return _pres(idm.get("officialTitle"))
    if E == "Brief Summary":
        return _pres((g(ps, "descriptionModule", "briefSummary") or "").strip())
    if E == "Primary Purpose":
        return _pres(di.get("primaryPurpose"))
    if E == "Study Design":
        return _pres(di.get("allocation") or di.get("interventionModel")
                     or g(di, "maskingInfo", "masking"))
    if E == "Study Phase":
        # "for an applicable drug clinical trial" — the reg's own qualifier, carried as
        # applies_note on the rule. A device-only or behavioural trial is not bound by it.
        if ovm.get("isFdaRegulatedDrug") is not True:
            return NA
        return _pres(dsm.get("phases"))
    if E == "Study Type":
        return _pres(dsm.get("studyType"))
    if E == "Pediatric Postmarket Surveillance of a Device Product":
        # Binds only a pediatric postmarket device surveillance. None of these records is one,
        # so this is NA everywhere — recorded honestly rather than scored as a free pass.
        return NA
    if E.startswith("Primary Disease or Condition"):
        return _pres(ps.get("conditionsModule", {}).get("conditions"))
    if E == "Intervention Name(s)":
        return _pres([i for i in ivs if i.get("name")]) if ivs else NA
    if E == "Other Intervention Name(s)":
        return _pres([i for i in ivs if i.get("otherNames")]) if ivs else NA
    if E == "Intervention Description":
        return _pres([i for i in ivs if i.get("description")]) if ivs else NA
    if E == "Intervention Type":
        return _pres([i for i in ivs if i.get("type")]) if ivs else NA
    if E == "Studies a U.S. FDA-regulated Device Product":
        return _pres(ovm.get("isFdaRegulatedDevice") is not None or None)
    if E == "Studies a U.S. FDA-regulated Drug Product":
        return _pres(ovm.get("isFdaRegulatedDrug") is not None or None)
    if E == "Device Product Not Approved or Cleared by U.S. FDA":
        if not any((i.get("type") or "").upper() == "DEVICE" for i in ivs):
            return NA
        return _pres(ovm.get("isUnapprovedDevice") is not None or None)
    if E == "Post Prior to U.S. FDA Approval or Clearance":
        if ovm.get("isUnapprovedDevice") is not True:
            return NA
        return NEVER
    if E == "Product Manufactured in and Exported from the U.S.":
        # The reg conditions this on there being no IND/IDE and no U.S. facility.
        has_ind = any(s.get("type") == "INDIDE" for s in (idm.get("secondaryIdInfos") or []))
        us_site = any((lo.get("country") or "") == "United States"
                      for lo in (clm.get("locations") or []))
        if has_ind or us_site:
            return NA
        return _pres(ovm.get("isUsExport") is not None or None)
    if E == "Study Start Date":
        return _pres(g(stm, "startDateStruct", "date"))
    if E == "Primary Completion Date":
        return _pres(g(stm, "primaryCompletionDateStruct", "date"))
    if E == "Study Completion Date":
        return _pres(g(stm, "completionDateStruct", "date"))
    if E == "Enrollment":
        en = dsm.get("enrollmentInfo") or {}
        if en.get("count") is None:
            return NEVER
        # §11.10(b): past the primary completion date the count must be the ACTUAL number.
        pcd = g(stm, "primaryCompletionDateStruct", "date")
        pcd_type = g(stm, "primaryCompletionDateStruct", "type")
        past = bool(pcd) and pcd_type == "ACTUAL"
        if past and (en.get("type") or "").upper() == "ESTIMATED":
            return BREACH
        return MET
    if E == "Primary Outcome Measure Information":
        return _pres(g(ps, "outcomesModule", "primaryOutcomes"))
    if E == "Secondary Outcome Measure Information":
        return _pres(g(ps, "outcomesModule", "secondaryOutcomes"))
    if E == "Eligibility Criteria":
        return _pres((em.get("eligibilityCriteria") or "").strip())
    if E == "Sex/Gender":
        return _pres(em.get("sex"))
    if E == "Age Limits":
        return _pres(em.get("minimumAge") or em.get("maximumAge"))
    if E == "Accepts Healthy Volunteers":
        return _pres(em.get("healthyVolunteers") is not None or None)
    if E == "Overall Recruitment Status":
        return _pres(status)
    if E == "Why Study Stopped":
        # The single most discriminating rule in the part, and the reason for this kit's corpus.
        if status not in STOPPED:
            return NA
        return MET if (stm.get("whyStopped") or "").strip() else BREACH
    if E == "Individual Site Status":
        locs = rendered_locations(clm)
        if not locs:
            return NEVER
        return MET if any(lo.get("status") for lo in locs) else BREACH
    if E == "Availability of Expanded Access":
        return _pres(g(stm, "expandedAccessInfo", "hasExpandedAccess") is not None or None)
    if E == "Name of the Sponsor":
        return _pres(g(scm, "leadSponsor", "name"))
    if E == "Responsible Party":
        rp = scm.get("responsibleParty") or {}
        if not rp.get("type"):
            return NEVER
        # The element is "Responsible Party, BY OFFICIAL TITLE". An entity satisfies it by name;
        # an individual investigator needs the official title the reg asks for.
        if rp["type"] in ("PRINCIPAL_INVESTIGATOR", "SPONSOR_INVESTIGATOR"):
            return MET if rp.get("investigatorTitle") else BREACH
        return MET
    if E == "Facility Information":
        # §11.10(b) spells the element out as parts: "(i) Facility Name, meaning the full name of
        # the organization where the clinical trial is being conducted; (ii) Facility Location …".
        # A site listed by city with no organisation name has addressed the element and failed
        # part (i) — a deficiency in a statement that exists, not silence.
        locs = rendered_locations(clm)
        if not locs:
            return NEVER
        return MET if all(lo.get("facility") for lo in locs) else BREACH
    if E == "Unique Protocol Identification Number":
        return _pres(g(idm, "orgStudyIdInfo", "id"))
    if E == "Secondary ID":
        return _pres(idm.get("secondaryIdInfos"))
    if E == "U.S. Food and Drug Administration IND or IDE Number":
        return _pres([s for s in (idm.get("secondaryIdInfos") or [])
                      if s.get("type") == "INDIDE"])
    if E == "Human Subjects Protection Review Board Status":
        # NOT EXPOSED by the public API at all — no field carries it on any of the 117 records
        # pulled. So it is never-addressed on every document, and that is a true statement about
        # these documents rather than a corpus defect. Left in the rulebook because dropping a
        # real rule to flatter a distribution is how a compliance kit stops being one.
        return NEVER
    if E == "Record Verification Date":
        return _pres(stm.get("statusVerifiedDate"))
    if E == "Responsible Party Contact Information":
        return _pres(clm.get("centralContacts"))
    raise SystemExit("no probe for element %r — the regulation gained an element and this kit "
                     "does not know how to check it. Add a probe rather than skipping it." % E)


# ── A BREACH BY OMISSION STILL POINTS AT THE DOCUMENT — it just points at a different line.
# Two of the three breach rules fire when a required element is ABSENT, so the element has no line
# of its own to quote. The first build failed on exactly that (`_verify` refused a breach with no
# quote) and the refusal was right: a finding a reader cannot locate in the document is not a
# finding. The fix is not to relax the check but to quote the line that CREATES the obligation,
# which is what a reviewer writing up the breach would cite:
#
#   Why Study Stopped      quote "Overall Recruitment Status: TERMINATED" — the status is what
#                          triggers §11.28(a)(2)(ii)(F); the explanation it demands is missing.
#   Individual Site Status quote the "Facility Information:" line — a facility is listed, and it
#                          carries no site status.
#
# The other breach rules (Enrollment, Responsible Party) are deficiencies in a statement that does
# exist, so they quote their own line and are absent from this map.
BREACH_EVIDENCE = {
    "Why Study Stopped": "Overall Recruitment Status",
    "Individual Site Status": "Facility Information",
}


def pick_evidence(element, verdict, ps, doc):
    """THE one place that decides which line a verdict points at.

    This started as a lookup in `main()` and grew a special case per rule until it was three
    conditionals deep in the middle of the write loop — at which point the third bug it caused
    was indistinguishable from the second. Every rule whose evidence is not simply "the line
    named after me" is handled here, once, next to the reason why.
    """
    if verdict not in (MET, BREACH):
        return ""
    clm = ps.get("contactsLocationsModule", {})

    # Site status is rendered as a SUFFIX inside its facility's line, never as a line of its own,
    # so neither verdict can quote an "Individual Site Status:" line — there is no such line.
    if element == "Individual Site Status":
        locs = rendered_locations(clm)
        want = (lambda lo: bool(lo.get("status"))) if verdict == MET else (lambda lo: True)
        lo = next((x for x in locs if want(x)), None)
        return "Facility Information: %s" % loc_value(lo) if lo else ""

    # Quote the site that is actually deficient. The first rendered location is usually a complete
    # one, and quoting it would show a line that looks fine underneath a breach.
    if element == "Facility Information" and verdict == BREACH:
        lo = next((x for x in rendered_locations(clm) if not x.get("facility")), None)
        if lo is not None:
            return "Facility Information: %s" % loc_value(lo)

    src = BREACH_EVIDENCE.get(element, element) if verdict == BREACH else element
    return evidence_for(src, doc)


def evidence_for(element, doc):
    """The document line that carries this element, quoted verbatim, or ''.

    Read out of the RENDERED TEXT, never rebuilt from the record — a quote the reader cannot find
    in the document is worse than no quote, and rebuilding is exactly how that happens.
    """
    key = element
    if key.startswith("Primary Disease or Condition"):
        key = "Primary Disease or Condition Being Studied in the Trial"
    for name in (key, key.replace("(s)", "")):
        for ln in doc.splitlines():
            if ln.startswith(name + ": "):
                return ln.strip()
    return ""


def _verify(nct, doc, rows):
    """Fail loudly rather than ship a wrong label."""
    for r in rows:
        v, ev = r["verdict"], r["evidence"]
        if v in (MET, BREACH):
            if not ev:
                raise SystemExit("%s: %s verdict on %r has no quote — a verdict about a statement "
                                 "must be able to point at the statement."
                                 % (nct, v, r["element"]))
            if ev not in doc:
                raise SystemExit("%s: %s quote %r is not in the document. The renderer and the "
                                 "prober have drifted." % (nct, v, ev[:60]))
        if v == NEVER:
            if ev:
                raise SystemExit("%s: never-addressed verdict on %r carries a quote %r — if a "
                                 "line exists the document is not silent."
                                 % (nct, r["element"], ev[:60]))
            if evidence_for(r["element"], doc):
                raise SystemExit("%s: %r labelled never-addressed but the document HAS a line for "
                                 "it. The probe disagrees with the renderer."
                                 % (nct, r["element"]))


# ── Selection. Greedy, deterministic, quota'd by status — see docs/CORPUS.md for the measurement
# that made it necessary.
def select(records, rules):
    """Greedy, deterministic, quota'd by status, on a LEXICOGRAPHIC objective.

    An earlier version maximised only "rules that vary", and it produced a corpus carrying 22
    breaches of which almost all were the same rule. Breach is the rarest verdict in this data —
    2.3% of the whole 117-record pool — because the registry enforces most of these elements at
    submission, so a selector that does not go looking for breaches will not find them.

    THE BREACHES ARE NOT MANUFACTURED. The obvious way to balance the classes is to perturb the
    documents, which is what UC007 does — but UC007 perturbs CLAIMS, text it generates itself,
    while here the document IS the evidence. Editing a federal record so it fails a rule would
    ship falsified public documents in a public repo to make a metric look better. So the
    selector takes every breach the real data contains and the eval reports the imbalance.

    Priority order, highest first:
      1. distinct (rule, breach) PAIRS covered — every breach rule represented beats many
         instances of one rule, and Individual Site Status alone accounts for 81 of the pool's 95
      2. rules that vary at all across the set
      3. raw breach count
    """
    for rec in records:
        rec["vec"] = tuple(probe(r["element"], rec["ps"], rec["doc"]) for r in rules)

    by_status = {}
    for r in records:
        by_status.setdefault(r["status"], []).append(r)
    for s in by_status:
        by_status[s].sort(key=lambda r: r["nct"])

    def objective(chosen):
        pairs, varying, breaches = set(), 0, 0
        for i in range(len(rules)):
            seen = set()
            for c in chosen:
                v = c["vec"][i]
                seen.add(v)
                if v == BREACH:
                    pairs.add(i)
                    breaches += 1
            seen.discard(NA)
            if len(seen) > 1:
                varying += 1
        return (len(pairs), varying, breaches)

    chosen, quota = [], {s: PER_STATUS for s in by_status}
    while sum(quota.values()) > 0:
        base, best, best_gain, best_s = objective(chosen), None, None, None
        for s, pool in by_status.items():
            if quota[s] == 0:
                continue
            for r in pool:
                if r in chosen:
                    continue
                cand = objective(chosen + [r])
                gain = tuple(a - b for a, b in zip(cand, base))
                # Ties broken by NCT, which `pool` is already sorted on, so the walk is stable.
                if best_gain is None or gain > best_gain:
                    best, best_gain, best_s = r, gain, s
        chosen.append(best)
        quota[best_s] -= 1
    return sorted(chosen, key=lambda r: r["nct"])


def main():
    rules = json.load(open(RULEBOOK, encoding="utf-8"))["rules"]
    os.makedirs(OUT, exist_ok=True)

    records = []
    for fn in sorted(f for f in os.listdir(RAW) if f.endswith(".json")):
        if fn.startswith("ecfr"):
            continue
        st = json.load(open(os.path.join(RAW, fn), encoding="utf-8"))
        ps = st.get("protocolSection", {})
        nct = g(ps, "identificationModule", "nctId")
        if not nct:
            continue
        records.append({"nct": nct, "ps": ps, "doc": render(st),
                        "status": g(ps, "statusModule", "overallStatus")})
    if not records:
        raise SystemExit("no records in data/_fetched/ — run `python -m tools.fetch_corpus` first.")

    chosen = select(records, rules)

    dist, applicable = {}, 0
    out_rows = []
    for rec in chosen:
        with open(os.path.join(OUT, rec["nct"] + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(rec["doc"])
        rows = []
        for r in rules:
            v = probe(r["element"], rec["ps"], rec["doc"])
            ev = pick_evidence(r["element"], v, rec["ps"], rec["doc"])
            rows.append({"rule": r["id"], "cite": r["cite"], "element": r["element"],
                         "verdict": v, "evidence": ev})
            dist[v] = dist.get(v, 0) + 1
            if v != NA:
                applicable += 1
        _verify(rec["nct"], rec["doc"], rows)
        out_rows.append({"doc": rec["nct"] + ".txt", "status": rec["status"], "verdicts": rows})

    with open(GOLD, "w", encoding="utf-8") as fh:
        for row in out_rows:
            fh.write(json.dumps(row) + "\n")

    print("corpus : %d documents -> data/corpus/" % len(out_rows))
    print("gold   : %d rule-verdicts (%d applicable) -> data/gold.jsonl"
          % (sum(dist.values()), applicable))
    for k in (MET, BREACH, NEVER, NA):
        n = dist.get(k, 0)
        print("   %-16s %4d  %5.1f%% of applicable"
              % (k, n, 100.0 * n / applicable if k != NA and applicable else 0.0))

    split_rules = 0
    for i, r in enumerate(rules):
        seen = {row["verdicts"][i]["verdict"] for row in out_rows}
        seen.discard(NA)
        if len(seen) > 1:
            split_rules += 1
    print("   rules that vary across the corpus: %d/%d" % (split_rules, len(rules)))


if __name__ == "__main__":
    main()
