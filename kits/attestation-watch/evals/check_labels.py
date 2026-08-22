"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                       # noqa: E402
from src import rulebook as RB                      # noqa: E402
from src.extract import compute as _compute         # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ SEVEN NULLABLE PER-PERSON FIELDS, AND EVERY NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   cycle_opened_on   null exactly where the roster line reads "cycle opened -- not recorded on
#                     this register" -- which happens for TWO different reasons and the roster
#                     line cannot tell you which.
#   return_filed_on   null where the Returns Filed section carries no line for this person.
#   return_covers_to  null where there is no return, or where the line says the covered period is
#                     not stated on the filed return. Those are different states and the rule
#                     treats them differently.
#   declared_relationship / earlier_declared_relationship / relationship_disposed_on / due_on
#                     null where the register carries nothing to read, or -- for due_on -- where
#                     nothing can be derived.
NULLABLE = {"cycle_opened_on", "return_filed_on", "return_covers_to", "declared_relationship",
            "earlier_declared_relationship", "relationship_disposed_on", "due_on"}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["register_id"]: r for r in rows}
    people = [(r["register_id"], p) for r in rows for p in r["attesters"]]

    if len(by_id) != len(rows):
        bad("duplicate register_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d register(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no register: %s" % (len(orphan), sorted(orphan)[:5]))

    for reg_id, r in sorted(by_id.items()):
        refs = [p["person_ref"] for p in r["attesters"]]
        if len(set(refs)) != len(refs):
            bad("%s: a person reference appears twice on one register — the whole scorer aligns "
                "rows by that key" % reg_id)
        if len(refs) < 3:
            bad("%s: only %d people on the register; the per-person graders need a roster"
                % (reg_id, len(refs)))

    for f in fields["register"]:
        n_null = sum(1 for r in rows if r.get(f["name"]) is None)
        if n_null:
            bad("register field %s is null in %d gold row(s) — no register-level field is nullable "
                "in this corpus" % (f["name"], n_null))

    for f in fields["attester"]:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for _reg, p in people if p.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold person row(s) — only %s are nullable in this corpus"
                % (f["name"], n_null, ", ".join(sorted(NULLABLE))))
        if f.get("values"):
            for reg_id, p in people:
                v = p.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s/%s: %s=%r is not one of %s"
                        % (reg_id, p["person_ref"], f["name"], v, f["values"]))

    # ⚑ GOLD MUST AGREE WITH ITS OWN RULE OUTPUT, ON BOTH THE STATUS AND THE DERIVED DATE. This is
    # the check that makes the whole kit honest: neither label is a second opinion about the
    # administrator's note, both are the rulebook run over the register's own values.
    dis_status = [(reg, p["person_ref"]) for reg, p in people
                  if RB.status_of(p) != p.get("status")]
    if dis_status:
        bad("%d gold person row(s) label a status their own values do not produce: %s"
            % (len(dis_status), dis_status[:5]))
    dis_due = [(reg, p["person_ref"]) for reg, p in people
               if RB.decide(p)["due_on"] != p.get("due_on")]
    if dis_due:
        bad("%d gold person row(s) carry a due date the derivation does not produce: %s"
            % (len(dis_due), dis_due[:5]))

    # ⚑ EVERY REQUIRED ATTESTER'S DUE DATE HAS PASSED AT THE AS-AT DATE. A "not due yet" case is a
    # seventh status this kit does not carry, so a corpus containing one would make `missing`
    # ambiguous. Asserted rather than assumed, because that limit is published on the kit page.
    not_yet = []
    for reg_id, p in people:
        due = p.get("due_on")
        if due and p.get("status") != "not_required" and due > by_id[reg_id]["as_at_date"]:
            not_yet.append((reg_id, p["person_ref"]))
    if not_yet:
        bad("%d person row(s) have a due date AFTER the register's as-at date — this corpus does "
            "not carry a 'not due yet' case and `missing` would be ambiguous on them: %s"
            % (len(not_yet), not_yet[:5]))

    # ⚑ THE HARD CASES, ASSERTED RATHER THAN TRUSTED. Each is a reading a careless monitor gets
    # wrong, and each has to be MEASURED rather than anecdotal, so each has a floor.
    n_reg = len(rows)

    joiner = [(r, p) for r, p in people if p["roster_event"] == "joined_mid_cycle"]
    no_cycle = [(r, p) for r, p in people
                if p["cycle_opened_on"] is None and p["roster_event"] == "none"]
    for reg_id, p in joiner:
        if p["status"] != "not_required":
            bad("%s/%s: a mid-cycle joiner owes nothing, gold says %r"
                % (reg_id, p["person_ref"], p["status"]))
        if p["cycle_opened_on"] is not None:
            bad("%s/%s: a mid-cycle joiner must carry the SAME unrecorded cycle line as the "
                "undeterminable rows, or the trap does not exist" % (reg_id, p["person_ref"]))
    for reg_id, p in no_cycle:
        if p["status"] != "not_determinable":
            bad("%s/%s: an unrecorded cycle with no roster event is not determinable, gold says %r"
                % (reg_id, p["person_ref"], p["status"]))
    if len(joiner) < 5 or len(no_cycle) < 5:
        bad("the same-roster-line trap needs at least 5 of each side and has %d joiner(s) and %d "
            "unreadable record(s)" % (len(joiner), len(no_cycle)))
    else:
        print("  info  %d mid-cycle joiner(s) and %d unreadable record(s) print the SAME roster "
              "line — only the Roster Changes section separates them" % (len(joiner), len(no_cycle)))

    vacated = [(r, p) for r, p in people if p["roster_event"] == "role_vacated"]
    for reg_id, p in vacated:
        if p["status"] != "not_required":
            bad("%s/%s: a vacated role owes nothing, gold says %r"
                % (reg_id, p["person_ref"], p["status"]))
    vacated_filed = [x for x in vacated if x[1]["return_filed_on"]]
    if len(vacated) < 5:
        bad("only %d vacated role(s) — the first false-alarm case needs at least 5" % len(vacated))
    else:
        print("  info  %d vacated role(s), %d of them with a return already on file"
              % (len(vacated), len(vacated_filed)))

    admin_rows = [(r, p) for r, p in people if p["role"] in RB.ROLES_NOT_REQUIRING]
    for reg_id, p in admin_rows:
        if p["status"] != "not_required":
            bad("%s/%s: a role the rulebook puts no requirement on owes nothing, gold says %r"
                % (reg_id, p["person_ref"], p["status"]))
        if p["due_on"] is not None:
            bad("%s/%s: no cycle length exists for this role, so no due date can be derived and "
                "gold must carry null" % (reg_id, p["person_ref"]))
    if len(admin_rows) < 5:
        bad("only %d row(s) carry a role with no attestation requirement — the third false-alarm "
            "case needs at least 5" % len(admin_rows))
    else:
        print("  info  %d row(s) carry a role the rulebook puts no requirement on, all with a null "
              "derived due date" % len(admin_rows))

    # ⚑ THE TWO DATE ORDERS. Same shape, opposite answer, and the ONLY thing that separates them
    # is which of two dates is earlier. Asserted directly, not hoped for.
    disposed_before = [(r, p) for r, p in people
                       if p["relationship_disposed_on"] and p["return_filed_on"]
                       and p["relationship_disposed_on"] < p["return_filed_on"]]
    disposed_after = [(r, p) for r, p in people
                      if p["relationship_disposed_on"] and p["return_filed_on"]
                      and p["relationship_disposed_on"] >= p["return_filed_on"]]
    for reg_id, p in disposed_before:
        if p["status"] != "contradicted":
            bad("%s/%s: a relationship disposed BEFORE the return that declares it is a "
                "contradiction, gold says %r" % (reg_id, p["person_ref"], p["status"]))
    for reg_id, p in disposed_after:
        if p["status"] != "satisfied":
            bad("%s/%s: a relationship disposed AFTER the return was filed is not a contradiction "
                "— the return was correct on the day it was filed — gold says %r"
                % (reg_id, p["person_ref"], p["status"]))
    if len(disposed_before) < 5 or len(disposed_after) < 5:
        bad("the two-date-order case needs at least 5 each way and has %d before / %d after"
            % (len(disposed_before), len(disposed_after)))
    else:
        print("  info  %d row(s) declare a relationship disposed BEFORE the return, %d AFTER it — "
              "same shape, opposite answer" % (len(disposed_before), len(disposed_after)))

    two_returns = [(r, p) for r, p in people if p["earlier_declared_relationship"]]
    for reg_id, p in two_returns:
        if p["status"] != "contradicted":
            bad("%s/%s: two returns that disagree are a contradiction, gold says %r"
                % (reg_id, p["person_ref"], p["status"]))
    if len(two_returns) < 5:
        bad("only %d row(s) carry two disagreeing returns — needs at least 5" % len(two_returns))
    else:
        print("  info  %d row(s) carry two returns from the same person that disagree"
              % len(two_returns))

    # A return filed AFTER the due date but inside the grace window is IN TIME. This is the false
    # alarm a queue makes when it compares two dates and stops there.
    in_grace = []
    for reg_id, p in people:
        if not (p["return_filed_on"] and p["due_on"]):
            continue
        limit = RB.iso(RB.stale_after(p["cycle_opened_on"], p["role"]))
        if limit and p["due_on"] < p["return_filed_on"] <= limit:
            in_grace.append((reg_id, p["person_ref"]))
            if p["status"] not in ("satisfied", "not_required"):
                bad("%s/%s: a return filed inside the grace window is in time, gold says %r"
                    % (reg_id, p["person_ref"], p["status"]))
    if len(in_grace) < 5:
        bad("only %d row(s) file inside the grace window — the looks-late-is-fine case needs at "
            "least 5" % len(in_grace))
    else:
        print("  info  %d row(s) filed AFTER the due date and inside the grace window — late to "
              "the eye, in time to the rulebook" % len(in_grace))

    wrong_period = [(r, p) for r, p in people
                    if p["return_covers_to"] and p["due_on"]
                    and p["return_covers_to"] < p["due_on"]]
    for reg_id, p in wrong_period:
        if p["status"] != "stale":
            bad("%s/%s: a return covering a period ending before the due date is stale, gold "
                "says %r" % (reg_id, p["person_ref"], p["status"]))
    if len(wrong_period) < 5:
        bad("only %d row(s) cover the wrong window — needs at least 5" % len(wrong_period))
    else:
        print("  info  %d row(s) were filed in time and attest to the PREVIOUS window"
              % len(wrong_period))

    # ⚑ NO GRADER MAY BE DEGENERATE. A status with no members, a constant worklist or a constant
    # routing flag would all score perfectly and mean nothing.
    counts = {}
    for _reg, p in people:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    for s in RB.STATUSES:
        if not counts.get(s):
            bad("gold has no %r rows — the six-way status grader would be degenerate" % s)
    print("  info  statuses: %s"
          % "  ".join("%s=%d" % (k, counts.get(k, 0)) for k in RB.STATUSES))

    n_work = sum(1 for _r, p in people if p["status"] in RB.WORKLIST)
    if n_work in (0, len(people)):
        bad("every person has the same worklist answer (%d of %d) — the false-alarm rate this kit "
            "exists to publish would be degenerate" % (n_work, len(people)))
    else:
        print("  info  %d of %d people need action today; %d do not, and THOSE are the rows a "
              "false alarm lands on" % (n_work, len(people), len(people) - n_work))

    n_flag = sum(1 for r in rows
                 if _compute([p["status"] for p in r["attesters"]]))
    if n_flag == 0 or n_flag == n_reg:
        bad("the pure-code owner-review flag is constant across gold (%d of %d) — it would score "
            "perfectly and mean nothing" % (n_flag, n_reg))
    else:
        print("  info  %d of %d registers need an owner rather than a reminder" % (n_flag, n_reg))
    for r in rows:
        if r["needs_owner_review"] != _compute([p["status"] for p in r["attesters"]]):
            bad("%s: the stored owner-review flag disagrees with its own statuses"
                % r["register_id"])

    # ⚑ THE DECOY MUST ACTUALLY BE A DECOY. A note register that agrees with the register's own
    # facts on every file is not planted ambiguity, it is decoration.
    contra = sum(1 for r in rows if r.get("contradicting_note"))
    if contra < 10:
        bad("only %d register(s) carry an administrator's note whose register contradicts the "
            "register's own facts — the decoy needs at least 10 to be measured" % contra)
    else:
        print("  info  %d of %d registers (%.0f%%) carry an administrator's note written in the "
              "register that contradicts their own facts"
              % (contra, n_reg, 100.0 * contra / n_reg))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL READER AND A DELIBERATE SHORTCUT, and this is the check
    # that says so -- written in from the start rather than found live. Its regexed values must
    # reproduce gold exactly, so the gap it opens is provably the DECIDING half and not the
    # reading half.
    try:
        from evals import baseline as B
    except ImportError as exc:
        print("  info  floor check skipped: %s" % exc)
    else:
        wrong_cells = 0
        for reg_id in sorted(docs):
            g = by_id[reg_id]
            r = B.extract(EX.load_doc(reg_id), fields)
            got = {a["person_ref"]: a for a in r["attesters"]}
            for f in fields["register"]:
                if (r["register"][f["name"]]["value"] or None) != (g.get(f["name"]) or None):
                    wrong_cells += 1
            for p in g["attesters"]:
                a = got.get(p["person_ref"])
                if a is None:
                    wrong_cells += 1
                    continue
                for f in fields["attester"]:
                    if f["name"] == "status":
                        continue                     # the floor's ONE deliberate shortcut
                    if (a["fields"][f["name"]]["value"] or None) != (p.get(f["name"]) or None):
                        wrong_cells += 1
        if wrong_cells:
            bad("the free floor misreads %d cell(s) it is supposed to regex perfectly — the gap "
                "it opens would then be a reading gap and not a deciding one" % wrong_cells)
        else:
            print("  info  the free floor reads every field except `status` exactly, on all %d "
                  "registers — so its whole failure is the shortcut, by construction" % n_reg)

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d register(s), %d attester row(s), %d register field(s) + %d per-person "
          "field(s); gold consistent with the corpus and with its own rule output"
          % (len(docs), len(people), len(fields["register"]), len(fields["attester"])))


if __name__ == "__main__":
    main()
