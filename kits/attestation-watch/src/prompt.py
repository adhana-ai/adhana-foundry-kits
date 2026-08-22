"""Assemble the register-monitoring prompt. ONE prompt per register, every person on it in one
reply.

⚠︎ THIS KIT WATCHES NOTHING. It reads one snapshot somebody else assembled and proposes a
worklist. The prompt says so, the UI says so and the kit's own pages say so: nothing here polls,
subscribes, schedules, alerts, escalates, chases, files, signs off or clears.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `status`, AND IT IS A FIVE-GATE RULE WITH A STOPPING ORDER. It
is stated in full, and THE RULEBOOK ITSELF IS SENT WITH IT, because the cycle lengths and the grace
window are a lookup and a model cannot look up a table it has never been shown. The alternative --
letting the model answer from whatever it thinks an attestation regime requires -- is exactly the
failure this kit exists to measure: the shipped rulebook is the authority for this decision, it is
an invention, and a reading that disagrees with it is wrong here even where the reasoning is
arguable.

Five things are spelled out that a model left to its own reading gets wrong:

  1. THE APPLICABILITY GATE COMES FIRST. A vacated role, a mid-cycle joiner and a role the rulebook
     puts no requirement on all owe nothing. All three have no return on file, and equating "no
     form" with "gap" is the single error that gets a monitoring queue ignored.
  2. THE SAME ROSTER LINE MEANS TWO DIFFERENT THINGS. `cycle opened -- not recorded on this
     register` appears both on somebody who joined last week and on a record nobody can read. Only
     the Roster Changes section separates them, and it is a different section.
  3. THE ORDER OF TWO DATES DECIDES A CONTRADICTION. A relationship disposed of BEFORE the return
     that declares it is a register contradicting itself. Disposed AFTER, the return was correct on
     the day it was filed, which is the only day a return can be correct about.
  4. THE DUE DATE IS DERIVED, NEVER READ. No register states it. It is the cycle-opened date plus
     the rulebook's cycle length for the role.
  5. THE ADMINISTRATOR'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. A settled-sounding note does not
     clear a gap and an alarmed one does not create one.

⚑ ONE CALL PER REGISTER, NOT ONE PER PERSON -- and unlike a per-field split this is not only a
cost decision. Two of the five gates read ACROSS people and sections (which of this person's two
returns is later; what the holdings section says about the relationship this return declares), so
a per-person call would have to carry most of the register anyway.
"""
import json

from .rulebook import RB, ROLES_REQUIRING, ROLES_NOT_REQUIRING, GRACE_DAYS

SYSTEM = (
    "You read ONE engagement's INDEPENDENCE ATTESTATION REGISTER -- a snapshot of who is on the "
    "engagement, what each of them has filed, and what the register records about their declared "
    "relationships -- and you extract structured fields from it. You return JSON and nothing "
    "else.\n"
    "\n"
    "You are PROPOSING a worklist for a qualified person to act on. You never chase anybody, "
    "never file anything, never sign a register off and never clear anyone. The rulebook below is "
    "an ILLUSTRATIVE rulebook shipped with this kit; it is not a professional standard and it is "
    "not an authority.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the register does not state a field, return null for it. Do not infer it and do not "
    "use what you know about the world.\n"
    "2. Return one object per person listed in `Attesters On Record`, in the order that section "
    "lists them, and no others. Never invent a person, and never drop one because there is "
    "nothing else on the register about them.\n"
    "3. `due_on` is DERIVED AND IS NEVER STATED ON THE REGISTER. Take the person's cycle-opened "
    "date and add the cycle length the rulebook gives for their role. Return null when the "
    "cycle-opened date is not recorded, and null when the rulebook gives no cycle length for the "
    "role.\n"
    "4. `status` is decided ONLY by the RULEBOOK given below. Work through these five gates IN "
    "ORDER and STOP at the first one that fires:\n"
    "   a. NOT REQUIRED. The Roster Changes section records this person's role as vacated, or "
    "records them as having joined inside the new-joiner window; or their role is one the rulebook "
    "puts no attestation requirement on. Answer 'not_required'. THIS GATE IS FIRST. All three of "
    "these people usually have no return on file, and treating that as a gap is the error this "
    "kit exists to measure.\n"
    "   b. NOT DETERMINABLE. The register does not record when this person's cycle opened, so no "
    "due date can be derived; or a return is on file and the register does not state what period "
    "it covers, so the coverage test cannot be run. Answer 'not_determinable'. This is a real "
    "answer, not a failure to produce one -- a confident wrong 'fine' is the expensive mistake "
    "here.\n"
    "   c. MISSING. No return is on file for this person at all. Answer 'missing'.\n"
    "   d. CONTRADICTED. The person has more than one return and the earlier one declares "
    "something different from the later one; or the latest return declares a relationship the "
    "holdings section records as DISPOSED ON A DATE BEFORE THE RETURN WAS FILED. Answer "
    "'contradicted'. A disposal recorded AFTER the filing date is NOT a contradiction -- the "
    "return was correct on the day it was filed.\n"
    "   e. STALE. The latest return was filed later than the due date plus the rulebook's grace "
    "window; or it covers a period ending BEFORE the due date, which attests to the previous "
    "cycle. Answer 'stale'.\n"
    "   Anything that survives all five gates is 'satisfied'.\n"
    "5. THE SAME ROSTER LINE MEANS TWO DIFFERENT THINGS. 'cycle opened -- not recorded on this "
    "register' appears both on somebody who joined mid-cycle and on a record nobody wrote a cycle "
    "date for. The line itself cannot tell you which. ONLY the Roster Changes section can, and it "
    "is a different section of the register.\n"
    "6. THE LATER FILING GOVERNS, AND THE RETURNS SECTION IS NOT SORTED. It is not grouped by "
    "person and not in date order. Read every line for a person before deciding which of them is "
    "their latest return; the earlier one is not discarded, it is compared against the later one.\n"
    "7. THE ADMINISTRATOR'S NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT ANYBODY'S STATUS. A note "
    "that sounds settled does NOT clear a gap, and a note that sounds worried does NOT create "
    "one. The register's own dates decide; the note is one person's remark and may disagree with "
    "them.\n"
    "8. Copy references, roles and declarations verbatim from the register, in the case it states "
    "them. Every date is yyyy-mm-dd.\n"
    "9. Use the exact allowed value for a field that lists them.\n"
    "10. Return every field named in the schema for every person, even when the answer is null."
)


def rulebook_block(rb=None):
    """The rulebook, rendered for the prompt out of data/rulebook.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of the cycle lengths inside this module is a
    copy that drifts from the file the corpus generator and the scorer both read -- which would
    make the model's instructions and the gold labels disagree about the same arithmetic,
    silently, and the disagreement would score as a model failure.
    """
    rb = rb or RB
    lines = ["ATTESTATION RULEBOOK %s (the authority for `status` and `due_on`; this is an "
             "ILLUSTRATIVE rulebook shipped with this kit, not a professional standard)"
             % rb["id"], "",
             "ROLES THAT CARRY AN ATTESTATION REQUIREMENT",
             "  " + ", ".join(ROLES_REQUIRING), "",
             "ROLES THAT CARRY NONE -- a person in one of these owes nothing, whatever the "
             "register lists",
             "  " + ", ".join(ROLES_NOT_REQUIRING), "",
             "CYCLE LENGTH, in days from the date the cycle OPENED to the date the attestation is "
             "DUE"]
    for role in ROLES_REQUIRING:
        lines.append("  %-24s %d days" % (role + ":", rb["cycle_days"][role]))
    lines += ["", "GRACE WINDOW",
              "  %d days after the due date. A return filed inside it is IN TIME." % GRACE_DAYS,
              "", "COVERAGE TEST", "  " + rb["coverage_rule"],
              "", "WHICH RETURN GOVERNS", "  " + rb["supersede_rule"],
              "", "THE TWO WAYS A REGISTER CONTRADICTS ITSELF"]
    for r in rb["contradiction_rules"]:
        lines.append("  - " + r)
    lines += ["", "THE SIX STATUSES", "  " + ", ".join(rb["statuses"]),
              "", "WHAT PUTS SOMEBODY ON THE WORKLIST",
              "  " + ", ".join(rb["worklist"]) + " -- " + rb["worklist_note"]]
    return "\n".join(lines)


RULEBOOK_TEXT = rulebook_block()


def field_schema(fields):
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    """fields is {"register": [...], "attester": [...]}. Returns (messages, parts, sections_used)."""
    reg_fields, att_fields = fields["register"], fields["attester"]
    names = [f["name"] for f in reg_fields] + [f["name"] for f in att_fields]
    wanted, seen = [], set()
    for name in names:
        for s in selector.for_field(secs, name):
            if s["start"] not in seen:
                seen.add(s["start"])
                wanted.append(s)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = ("REGISTER-LEVEL FIELDS -- one value each, for the whole register\n%s\n\n"
              "PER-ATTESTER FIELDS -- one object per person listed in Attesters On Record\n%s"
              % (field_schema(reg_fields), field_schema(att_fields)))

    shape = ('{"%s": ..., "attesters": [{"%s": ...}, ...]}'
             % ('": ..., "'.join(f["name"] for f in reg_fields),
                '": ..., "'.join(f["name"] for f in att_fields)))

    user = ("%s\n\n"
            "Extract these fields:\n%s\n\n"
            "Return a JSON object of exactly this shape:\n%s\n"
            "Use null for any field the register does not state.\n\n"
            "ATTESTATION REGISTER\n--------------------\n%s\n"
            % (RULEBOOK_TEXT, schema, shape, context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "attestation rulebook", "text": RULEBOOK_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "register sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    """The reply -> (register values, [attester values]). Fails closed to ({}, []).

    ⚠︎ A REPLY THAT CARRIES NO `attesters` LIST IS A FAILED DOCUMENT, NOT AN EMPTY REGISTER. Every
    register in this corpus has at least four people on it, so an empty list is a parse failure
    wearing the shape of an answer -- and on a monitoring queue "nobody needs chasing here" is
    exactly the wrong thing to say by accident.
    """
    reg_fields, att_fields = fields["register"], fields["attester"]
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}, []
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}, []
    if not isinstance(obj, dict):
        return {}, []
    reg = {f["name"]: obj.get(f["name"]) for f in reg_fields}
    rows = obj.get("attesters")
    if not isinstance(rows, list):
        return reg, []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append({f["name"]: r.get(f["name"]) for f in att_fields})
    return reg, out
