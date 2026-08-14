"""Sixty short internal policy documents, one change request each, and the exact bytes each
document should end up as.

⚑ THIS IS THE FIRST KIT HERE WHOSE OUTPUT IS AN ARTIFACT RATHER THAN A JUDGEMENT.
The other fourteen read a document and return an opinion about it — a label, a score, a set of
fields. This one returns a DOCUMENT: the same policy with one clause changed. That moves the
question from "was the answer right" to "is the file now correct", and it brings a failure mode
none of the others can have — the change lands correctly AND something else moves at the same time.

⚑ SO THE GOLD IS BYTES, NOT A LABEL. Every request carries the exact text the document should hold
afterwards, authored at generation time. There is no fuzzy credit: either the file matches or it
does not, and the diff says precisely where it did not.

⚑ AND A THIRD OF THE REQUESTS MUST PRODUCE NO WRITE AT ALL. A kit that only measures whether an
edit was applied rewards a system that always edits. The expensive real failure is the opposite:
confidently writing a change that should have been refused. Three refusal families, planted
deliberately:

    ambiguous      the description matches TWO clauses, so the target cannot be known
    missing        the clause described is not in the document
    contradiction  the change would orphan a cross-reference elsewhere in the document

⚠︎ THE THIRD IS THE ONE THAT SEPARATES THE TWO METHODS, and it is the reason the kit is worth
running. A find-and-replace can see that an anchor is ambiguous or absent — it counts matches. It
cannot see that clause 5 says "any exception to clause 4" and that deleting clause 4 therefore
breaks the document. That needs the whole page read, which is what the model is for.
"""
import random

SEED = 20260815
N_DOCS = 60

ORGS = ["Northgate Industries", "Bellamy Freight", "Cordell Manufacturing", "Duxbury Health",
        "Everly Retail Group", "Fenwick Chemicals", "Glenmoor Utilities", "Hartwell Logistics",
        "Ivorydale Foods", "Jessup Engineering", "Kelmscott Media", "Langford Marine"]

POLICIES = [
    ("TRAVEL AND EXPENSE POLICY", "POL"),
    ("INFORMATION HANDLING POLICY", "IHP"),
    ("SUPPLIER ONBOARDING PROCEDURE", "SOP"),
    ("INCIDENT REPORTING PROCEDURE", "IRP"),
]

# Each clause is (heading, template, knob). `knob` names the number this clause owns, so a change
# request can target it precisely and the gold can be written by substitution rather than by hand.
CLAUSES = [
    ("Scope", "This policy applies to all employees and contractors of {org}.", None),
    ("Approval", "Any commitment above {approval} {ccy} requires written approval from a line "
                 "manager before it is made.", "approval"),
    ("Notice", "Requests must be raised at least {notice} working days before the date they "
               "take effect.", "notice"),
    ("Submission", "Completed records must be submitted within {submit} days of the event they "
                   "describe.", "submit"),
    ("Retention", "Records under this document are retained for {retain} months and then "
                  "destroyed.", "retain"),
]

# Clause 6 exists only to create the cross-reference that makes the contradiction family real.
XREF = ("Exceptions", "Any exception to clause {ref} must be approved in writing by the "
                      "Compliance team and recorded on the exception register.")


def _doc_text(d):
    lines = [
        "%s — %s" % (d["org"].upper(), d["policy"]),
        "Document ref: %s-%04d   ·   Version %d" % (d["prefix"], d["ref"], d["version"]),
        "Effective: %s" % d["effective"],
        "",
    ]
    for i, (head, body) in enumerate(d["clauses"], 1):
        lines.append("%d. %s" % (i, head))
        lines.append("   %s" % body)
        lines.append("")
    lines.append("Issued by the Operations Office. Questions to operations@%s.example"
                 % d["org"].split()[0].lower())
    # ⚑ TRAILING NEWLINE, DELIBERATELY. A text file ends with one, and a model returning the
    # document will naturally produce one. Without it here, gold and a perfectly correct answer
    # would differ by a byte that has nothing to do with the edit — the scorer normalises trailing
    # whitespace as well, because being right for two reasons is cheaper than being wrong for one.
    return "\n".join(lines) + "\n"


def make_documents():
    """Sixty documents, each with one change request and its expected result. Pure function of SEED.

    ⚑ THE REQUEST FAMILIES ARE DEALT ROUND-ROBIN, NOT DRAWN AT RANDOM. A random draw over 60
    documents would leave the refusal families with counts nobody chose — and every rate this kit
    publishes has one of those counts as its denominator. Dealing them fixes the denominators in
    advance: **36 that must be applied and 24 that must be refused**, the refusals split 8 / 8 / 8
    across ambiguous, missing and contradiction. Those three eights are the denominators of every
    refusal rate this kit publishes, and they are small — a rate over 8 is one row away from moving
    12.5 points, which the pages say rather than leave to be inferred.
    """
    rng = random.Random(SEED)
    docs = []
    families = (["apply"] * 4 + ["ambiguous", "missing", "contradiction"]) * 9
    for i in range(N_DOCS):
        org = ORGS[i % len(ORGS)]
        policy, prefix = POLICIES[i % len(POLICIES)]
        knobs = {"approval": rng.choice([250, 500, 750, 1000, 2500]),
                 "notice": rng.choice([5, 7, 10, 14, 21]),
                 "submit": rng.choice([14, 21, 30, 45, 60]),
                 "retain": rng.choice([12, 24, 36, 60, 84])}
        ccy = rng.choice(["USD", "EUR", "GBP"])
        fam = families[i]

        clauses = [(h, t.format(org=org, ccy=ccy, **knobs)) for h, t, _k in CLAUSES]
        # The cross-reference clause always points at Submission (clause 4). Its presence is what
        # makes "delete clause 4" a contradiction rather than a simple deletion.
        clauses.append((XREF[0], XREF[1].format(ref=4)))

        d = {"doc_id": "p%03d" % i, "org": org, "policy": policy, "prefix": prefix,
             "ref": rng.randint(100, 9999), "version": rng.randint(1, 6),
             "effective": "2026-%02d-%02d" % (rng.randint(1, 8), rng.randint(1, 28)),
             "clauses": clauses, "family": fam, "ccy": ccy, "knobs": knobs}
        d["before"] = _doc_text(d)

        if fam == "apply":
            # A precise, single-target change: one knob, named by its clause number and heading.
            knob, cl_no = rng.choice([("approval", 2), ("notice", 3), ("submit", 4), ("retain", 5)])
            old = knobs[knob]
            new = {"approval": old + rng.choice([250, 500]),
                   "notice": old + rng.choice([3, 7]),
                   "submit": old + rng.choice([15, 30]),
                   "retain": old + rng.choice([12, 24])}[knob]
            after = dict(knobs, **{knob: new})
            nd = dict(d, clauses=[(h, t.format(org=org, ccy=ccy, **after))
                                  for h, t, _k in CLAUSES] + [(XREF[0], XREF[1].format(ref=4))])
            d["after"] = _doc_text(nd)
            d["request"] = ("In clause %d (%s), change %s to %s."
                            % (cl_no, CLAUSES[cl_no - 1][0], old, new))
            d["should_write"] = True
            d["why"] = None
        else:
            d["after"] = d["before"]          # a refusal means the file is left EXACTLY as it was
            d["should_write"] = False
            if fam == "ambiguous":
                # Two clauses now carry the same number, so "change 30 to 45" names neither.
                dup = rng.choice(["notice", "submit", "retain"])
                other = [k for k in ("notice", "submit", "retain") if k != dup][0]
                knobs2 = dict(knobs, **{other: knobs[dup]})
                d["clauses"] = [(h, t.format(org=org, ccy=ccy, **knobs2))
                                for h, t, _k in CLAUSES] + [(XREF[0], XREF[1].format(ref=4))]
                d["before"] = d["after"] = _doc_text(d)
                d["request"] = ("Change the %d in this document to %d."
                                % (knobs[dup], knobs[dup] + 10))
                d["why"] = ("two clauses state %d, so the request names neither of them"
                            % knobs[dup])
            elif fam == "missing":
                d["request"] = ("In clause 9 (Escalation), change the response time to 4 hours.")
                d["why"] = "there is no clause 9 in this document — it has six"
            else:
                d["request"] = "Delete clause 4 entirely."
                d["why"] = ("clause 6 says any exception to clause 4 must be approved, so "
                            "deleting clause 4 leaves that reference pointing at nothing")
        docs.append(d)
    return docs
