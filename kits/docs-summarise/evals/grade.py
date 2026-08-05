"""Grade a run's briefs against the weighted rubric. THE GRADER IS A PERSON — this is the prompt
that puts one in front of the evidence and records what they said.

Usage:
    python -m evals.grade --run-id r001-<model>              # grade every brief, section by section
    python -m evals.grade --run-id r001-<model> --grader b   # the second grader, for agreement
    python -m evals.grade --run-id r001-<model> --resume     # pick up where you stopped
    python -m evals.grade --run-id r001-<model> --report     # score what has been graded so far

⚑ WHY THIS FILE EXISTS AND `evals/judge.py` DOES NOT.
UC001 grades with an LLM judge; UC002 compares strings to a gold record. Both are code, and both
are correct for their use case. Neither works here: two correct summaries of one document share
almost no words, so there is no string to match — and asking a model to score a model's summary
would make the headline figure a measurement of the judge, which the kit standard's own rule
covers in four words: NO METHOD VALIDATES ITSELF.

So the score comes from a person, and everything in this file exists to make that cheap and
honest rather than to hide it. The cost unit is `reviewer-minutes`, and this is the thing that
spends them.

⚠︎ IT TIMES ITSELF, AND THAT IS NOT A GIMMICK. `reviewer-minutes` has never been used by any kit
in this estate, and the standard already warns what happens when a manual method is priced in
tokens: it reads as $0.00, which is not cheap, it is UNPRICED. The only way the Cost board can
print an honest figure is if something counted. Seconds per section are recorded as they are
given, so the published number is measured rather than estimated by whoever writes the page.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import summarise as SM                 # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
REF = os.path.join(HERE, "data", "reference")


def grade_path(run_id, grader):
    return os.path.join(RESULTS, "grades-%s-%s.json" % (run_id, grader))


def load_run(run_id):
    p = os.path.join(RESULTS, "eval-%s.json" % run_id)
    if not os.path.exists(p):
        raise SystemExit("no run record at %s. Run `python -m evals.run --run-id %s` first."
                         % (os.path.relpath(p, HERE), run_id))
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# How many unusable answers in a row before this stops asking. A person who cannot answer stops on
# their own; a stream of queued newlines does not, and scrolling the document they were reading off
# the top of the terminal is the one thing that makes this job harder than it already is.
GIVE_UP_AFTER = 3


def _ask(prompt_text, valid):
    """Read one grade. An unreadable answer is asked again rather than defaulted — a default here
    would silently put a number nobody gave into a published figure.

    ⚠︎ THE HINT WAS BUILT FROM THE `valid` SET AND PRINTED IN A DIFFERENT ORDER EVERY RUN —
    "3, 2, 5, 4, s, 0, 1", then "3, 5, 2, 1, 0, 4, s" the next time, because Python randomises
    string hashing per process. A 0-5 scale is an ORDERED thing, and this is the line a grader
    looks at more than any other; shuffling it makes them re-read it every time. Sorted now:
    digits ascending, 's' last.

    ⚠︎ AND IT SPUN. Every empty line consumed one cycle and re-printed the hint, silently, for as
    long as input kept arriving — a paste carrying trailing newlines produced a wall of a dozen
    identical prompts and pushed the document being graded off the screen. The loop did exactly
    what it was written to do, which is why nothing caught it and why the fix is a stop condition
    rather than a correction.
    """
    hint = ", ".join(sorted(valid, key=lambda v: (not v.isdigit(), v)))
    misses = 0
    while True:
        try:
            raw = input(prompt_text).strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nstopped. Nothing is lost — rerun with --resume.")
        if raw in valid:
            return raw
        misses += 1
        if misses >= GIVE_UP_AFTER:
            raise SystemExit(
                "\n%d unusable answers in a row — stopping rather than filling the screen.\n"
                "Expected one of: %s\n"
                "If those arrived as a paste, the trailing newlines were read as answers. NOTHING "
                "WAS RECORDED for them — a blank is not a grade.\n"
                "Nothing is lost — rerun with --resume." % (misses, hint))
        print("   (enter one of: %s)" % hint)


def score(run, grades, sections):
    """Weighted score per document and overall, plus the honest denominators.

    ⚑ AN ABSENT SECTION SCORES 0 AND IS COUNTED SEPARATELY. Averaging it away would let a model
    that skipped two sections outscore one that attempted all six badly, which is backwards: the
    brief is a FIXED SHAPE and not filling it is the failure the shape exists to expose.

    ⚠︎ AND A DOCUMENT THAT WAS NEVER GRADED IS NOT A ZERO. It is excluded from the denominator and
    counted in `ungraded`. This kit's whole argument is that a missing measurement and a bad
    measurement are different facts.
    """
    weights = {s["key"]: s["weight"] for s in sections}
    total_weight = sum(weights.values())
    per_doc, ungraded, absent, minutes = {}, [], 0, 0.0
    for doc_id, rec in (run.get("records") or {}).items():
        g = grades.get(doc_id)
        if not g or not g.get("sections"):
            ungraded.append(doc_id)
            continue
        earned = 0.0
        for key, w in weights.items():
            sec = rec["sections"].get(key) or {}
            got = g["sections"].get(key)
            if sec.get("state") in ("absent", "missing"):
                absent += 1
                continue                        # 0 of w, counted, never averaged away
            if got is None:
                continue
            earned += w * (int(got) / 5.0)
        per_doc[doc_id] = round(earned, 2)
        minutes += (g.get("seconds") or 0) / 60.0

    scores = sorted(per_doc.values())
    mean = round(sum(scores) / len(scores), 2) if scores else None
    return {
        "graded_documents": len(per_doc),
        "ungraded_documents": ungraded,
        "weighted_mean": mean,
        "weighted_max": total_weight,
        "median": scores[len(scores) // 2] if scores else None,
        "worst": scores[0] if scores else None,
        "best": scores[-1] if scores else None,
        "absent_sections": absent,
        "per_document": per_doc,
        # THE COST UNIT, MEASURED. Not "about ten minutes a document" — the seconds this grader
        # actually spent, summed. It is what the Cost board prices, and it is the only number in
        # this kit that no model produced.
        "reviewer_minutes": round(minutes, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--grader", default="a",
                    help="who is grading. Two graders on a subset is what lets the Evals board "
                         "print an agreement figure; one grader means it must say it did not "
                         "measure agreement, which is a worse page but a true one.")
    ap.add_argument("--limit", type=int, default=0, help="grade the first N documents only")
    ap.add_argument("--resume", action="store_true", help="skip documents already graded")
    ap.add_argument("--report", action="store_true", help="score what exists, grade nothing")
    a = ap.parse_args()

    run = load_run(a.run_id)
    sections = SM.sections_spec()
    scale = SM.load_rubric()["scale"]
    path = grade_path(a.run_id, a.grader)
    grades = json.load(open(path, encoding="utf-8"))["grades"] if os.path.exists(path) else {}

    if a.report:
        out = score(run, grades, sections)
        print(json.dumps(out, indent=1))
        return

    docs = list((run.get("records") or {}).keys())
    if a.limit:
        docs = docs[:a.limit]
    todo = [d for d in docs if not (a.resume and d in grades)]
    if not todo:
        print("nothing to grade — all %d document(s) already have grades from %s."
              % (len(docs), a.grader))
        return

    # ⚑ A PERSON GRADES THIS, SO A PERSON HAS TO BE AT THE KEYBOARD. Everything below reads
    # stdin and writes whatever it gets into a published figure. Piped in, `yes 4 | ...` scores a
    # whole run in a second and the record would name a grader who never read a word — the exact
    # failure `_ask` refuses to commit by defaulting, arriving through the door next to it. Refused
    # up front rather than discovered in a grades file that looks like work.
    if not sys.stdin.isatty():
        raise SystemExit(
            "stdin is not a terminal, so nothing here is a person's judgement. Grading is manual "
            "by design: two correct summaries of one document share almost no words, so there is "
            "nothing to match against, and scoring a model with a model measures the judge.\n"
            "Run this in a terminal. For a score over grades that already exist, use --report, "
            "which grades nothing and is safe to pipe.")

    print("Grading %d brief(s) from run %s as grader '%s'." % (len(todo), a.run_id, a.grader))
    print("Scale: " + "  ".join("%s=%s" % (k, v.split(",")[0].split("—")[0].strip())
                                for k, v in sorted(scale["anchors"].items())))
    print("Enter a digit 0-5, or 's' to skip a section, or ctrl-C to stop (nothing is lost).\n")

    for n, doc_id in enumerate(todo, 1):
        rec = run["records"][doc_id]
        print("=" * 78)
        print("[%d/%d]  %s" % (n, len(todo), doc_id))
        ref = os.path.join(REF, "%s.txt" % doc_id)
        if os.path.exists(ref):
            # ⚠︎ OFFERED, NEVER SHOWN FIRST, AND NEVER GOLD. The reference is the SOURCE's own
            # brief — the abstract and Highlights block build_corpus stripped out. It answers
            # different questions in a different order, so a grader who reads it first starts
            # scoring the model on how closely it imitates GAO's house style. It is here for
            # calibration when a grader is unsure what the document even said.
            print("     (a reference brief written by the source is at %s — read it only if you "
                   "need to calibrate, and never score against it)" % os.path.relpath(ref, HERE))
        print("=" * 78)

        got, t0 = {}, time.time()
        for s in sections:
            sec = rec["sections"].get(s["key"]) or {}
            print("\n--- %s   (weight %d)" % (s["name"], s["weight"]))
            print("    asks: %s" % s.get("asks", ""))
            if sec.get("state") == "absent":
                print("    [the model declined this section — scored 0, nothing to grade]")
                got[s["key"]] = None
                continue
            if sec.get("state") == "missing":
                print("    [no such section in the reply — a parsing fault, not a judgement]")
                got[s["key"]] = None
                continue
            print("\n" + (sec.get("text") or "").strip() + "\n")
            ans = _ask("    grade 0-5 (s to skip): ", {"0", "1", "2", "3", "4", "5", "s"})
            got[s["key"]] = None if ans == "s" else int(ans)

        grades[doc_id] = {"grader": a.grader, "sections": got,
                          "seconds": round(time.time() - t0, 1)}
        os.makedirs(RESULTS, exist_ok=True)
        # Written after every document, not at the end. A grading session is long and a person
        # will stop halfway; losing forty minutes of somebody's reading to a ctrl-C would make
        # the cost unit a punishment.
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"run_id": a.run_id, "grader": a.grader, "grades": grades}, f, indent=1,
                      ensure_ascii=False)
        print("\n  saved (%s so far) -> %s"
              % (len(grades), os.path.relpath(path, HERE)))

    out = score(run, grades, sections)
    print("\n%-24s %s of %s" % ("weighted mean", out["weighted_mean"], out["weighted_max"]))
    print("%-24s %s" % ("documents graded", out["graded_documents"]))
    print("%-24s %s" % ("sections the model skipped", out["absent_sections"]))
    print("%-24s %s" % ("reviewer-minutes spent", out["reviewer_minutes"]))


if __name__ == "__main__":
    main()
