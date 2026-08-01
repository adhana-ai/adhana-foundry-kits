"""The correctness grader. Reads a completed run and re-scores every answer with a model.

WHY THIS EXISTS: FOUR ARTIFACTS OUT OF ONE INSTRUMENT.
`run.py` grades by exact substring -- an answer is correct if it contains a required fragment.
That is cheap, deterministic and needs no key, and it has now produced four different wrong
numbers, each one discovered only after the previous fix:

  1. HEADING FRAGMENTS.  `answer_contains: ["querying an r*tree index"]` was a table-of-contents
     entry. It passed check 2 -- the string really is in the document -- and then marked every
     correct prose answer wrong.
  2. FRAGMENT LENGTH.    Measured over 100 graded answers: 80% correct at 1-2 word fragments,
     33% at 7+. Same answers. The ruler was scoring label verbosity. Fixed by MAX_FRAGMENT_WORDS.
  3. TERSENESS.          A polar question -- "Does WAL mode affect concurrency?" -- has a correct
     one-word answer. "Yes." contains no fragment and was marked wrong, so the grader rewarded
     padding. Fixed by check 6, which forbids the question shape.
  4. PARAPHRASE RIGIDITY. This one. Fixing 3 required rewriting 14 questions, and the fragments
     chosen for them were the DOCUMENT's phrasing rather than an answer's. The docs say an index
     is "formed on expressions"; a correct answer says it "can reference expressions involving
     table columns" and scores zero. Measured on the re-capture: of pro's 6 failures 4 were
     correct answers, of flash's 8 six were. Both models sit near 86% true accuracy while the
     substring grader reported 78% and 74% -- and reported them in the wrong ORDER.

That last point is the one that matters. The artifact did not merely add noise, it INVERTED the
ranking: on the polar labels flash scored 86% and pro 74%, because flash wrote longer answers.
A model comparison is the entire teaching point of lens 06. An instrument that reverses it is not
imprecise, it is wrong, and no amount of relabelling has fixed it in four attempts.

So the substring check stops being the correctness grader. It keeps a job -- see below -- and a
model takes over the judgement it was never able to make.

WHAT THIS DOES NOT DO, AND WHY THAT IS DELIBERATE.
A judge is not free and it is not truth. It costs a call per row, it brings its own error, and it
can be wrong in ways a substring never is -- it can be talked round by a confident wrong answer.
Three things keep it honest here:

  - IT NEVER SEES THE FRAGMENT. The judge is given the question and the reference answer, and
    nothing else. Showing it `answer_contains` would rebuild the instrument being replaced, and
    the agreement rate below would then measure nothing.
  - THE SUBSTRING CHECK STILL RUNS, as a GROUNDING signal rather than a correctness one. It answers
    a different and still-useful question: did the expected content actually reach the answer
    verbatim. Both are recorded per row, and every DISAGREEMENT is listed, because the disagreements
    are where one of the two graders is wrong and a human should look.
  - IT IS PROVED RED BEFORE IT IS TRUSTED GREEN. `--self-test` sends known-wrong answers and fails
    if the judge passes them. A grader that cannot fail anything reports 100% and means nothing --
    this repo has already shipped one gate whose default argument made it a permanent no-op.

Automation runs on DeepSeek here, by standing rule, and judging is automation.

Usage:
    python evals/judge.py results/eval-deepseek-v4-pro.json      # needs a key
    python evals/judge.py --self-test                            # prove it can go red
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_labels                                  # noqa: E402
from src import config                                                      # noqa: E402
from src.adapters import complete                                           # noqa: E402

# The verdict is a boolean and one sentence, so 400 tokens looked generous. It was not, and the
# way it failed is worth recording: 3 of 50 rows came back empty or cut off mid-JSON --
# '{"correct": true, "reason": "Both' -- because the model spends budget thinking before it emits,
# and the ceiling is on the whole completion, not on the part we wanted.
#
# The fix is the one this estate already paid for once, in the daily-brief pipeline: A RETRY THAT
# REPEATS THE REFUSED CONDITION IS NOT A RETRY. Re-rolling at 400 would have produced the identical
# deterministic failure three more times. So the ceiling ESCALATES, and only an unreadable verdict
# triggers it -- a judge that says "false" is not retried, or the grader would be shopping for the
# answer it prefers.
VERDICT_TOKEN_SCALE = (400, 1200, 3000)

SYSTEM = (
    "You grade answers to questions about SQLite's documentation. You are given a QUESTION, a "
    "REFERENCE ANSWER written by a human from the source document, and a CANDIDATE ANSWER produced "
    "by a system under test.\n\n"
    "Decide whether the CANDIDATE is correct: does it convey the substance of the REFERENCE?\n\n"
    "Rules:\n"
    "- Judge MEANING, not wording. A correct paraphrase is correct. Different phrasing, synonyms, "
    "reordering, extra correct detail, and markdown formatting are all fine.\n"
    "- The candidate does NOT need to be complete. If it answers the question correctly as far as "
    "it goes, it is correct. Brevity is not an error.\n"
    "- It IS incorrect if it contradicts the reference, states the opposite polarity, names the "
    "wrong thing, is empty, or answers a different question.\n"
    "- Citation markers like [1] or [4] are formatting. Ignore them.\n"
    "- An empty or content-free candidate is incorrect.\n\n"
    'Reply with ONLY a JSON object, no prose and no code fence: {"correct": true|false, '
    '"reason": "<one short sentence>"}'
)

_JSON = re.compile(r"\{.*\}", re.S)


def _read_verdict(text):
    """Parse one reply. Returns (correct|None, reason); None means it could not be read."""
    text = (text or "").strip()
    if not text:
        return None, "judge returned an empty completion"
    m = _JSON.search(text)
    if not m:
        return None, "judge returned no JSON: %r" % text[:120]
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, "judge returned truncated or unparseable JSON: %r" % text[:120]
    if not isinstance(obj.get("correct"), bool):
        return None, "judge omitted a boolean 'correct': %r" % text[:120]
    return obj["correct"], str(obj.get("reason", ""))[:300]


def _verdict(cfg, question, reference, candidate):
    """One judgement, escalating the token ceiling while the reply is unreadable.

    Returns (correct|None, reason). None survives all escalations and is recorded as such rather
    than silently coerced to False: a parse failure is not a wrong answer, and counting it as one
    would understate the system under test and flatter the grader."""
    user = ("QUESTION:\n%s\n\nREFERENCE ANSWER:\n%s\n\nCANDIDATE ANSWER:\n%s"
            % (question, reference, candidate if candidate.strip() else "(empty)"))
    reason = "not attempted"
    for ceiling in VERDICT_TOKEN_SCALE:
        got = complete(cfg, SYSTEM, user, max_tokens=ceiling)
        correct, reason = _read_verdict(got.get("text"))
        if correct is not None:
            return correct, reason
    return None, "%s (unreadable at every ceiling up to %d)" % (reason, VERDICT_TOKEN_SCALE[-1])


# Known-wrong answers. Each is fluent, on-topic and confidently phrased -- the failure mode a
# judge actually has -- so passing them all is evidence the judge discriminates rather than
# evidence the fixtures were easy.
SELF_TEST = [
    {"q": "How does WAL mode change the blocking relationship between readers and writers?",
     "ref": "Readers do not block writers and a writer does not block readers, so reading and "
            "writing can proceed concurrently.",
     "cand": "In WAL mode readers block writers and writers block readers, so all access is "
             "serialised one connection at a time.",
     "expect": False, "why": "opposite polarity, stated fluently"},
    {"q": "What condition must be met before SQLite's built-in math functions will work?",
     "ref": "The amalgamation must be compiled with the -DSQLITE_ENABLE_MATH_FUNCTIONS "
            "compile-time option.",
     "cand": "They are available by default in every build of SQLite and need no compile-time "
             "option.",
     "expect": False, "why": "confidently wrong on the only fact asked for"},
    {"q": "What does fuzz testing seek to establish about SQLite?",
     "ref": "That SQLite responds correctly to invalid, out-of-range, or malformed inputs.",
     "cand": "SQLite is written in C and has over 600 times as much test code as library code.",
     "expect": False, "why": "true, on-topic, and answers a different question"},
    {"q": "What does fuzz testing seek to establish about SQLite?",
     "ref": "That SQLite responds correctly to invalid, out-of-range, or malformed inputs.",
     "cand": "", "expect": False, "why": "empty"},
    # Two that MUST pass, or the judge is simply strict rather than discriminating -- and a grader
    # that fails everything is exactly as useless as one that passes everything.
    {"q": "How does WAL mode change the blocking relationship between readers and writers?",
     "ref": "Readers do not block writers and a writer does not block readers, so reading and "
            "writing can proceed concurrently.",
     "cand": "In WAL mode, readers and writers do not block each other; they can run at the same "
             "time. [1][4]",
     "expect": True, "why": "correct paraphrase -- the exact case the substring grader failed"},
    {"q": "Besides the columns of a table, what else can an SQLite index reference?",
     "ref": "An index can be formed on expressions involving table columns.",
     "cand": "An SQLite index can also reference expressions involving table columns.",
     "expect": True, "why": "correct paraphrase in different words"},
]


def self_test(cfg):
    print("SELF-TEST -- the judge must reject fluent wrong answers and accept correct paraphrases.")
    bad = 0
    for i, c in enumerate(SELF_TEST, 1):
        correct, reason = _verdict(cfg, c["q"], c["ref"], c["cand"])
        ok = correct is c["expect"]
        bad += not ok
        print("  %d. %-5s expected=%-5s got=%-5s  %s" % (
            i, "PASS" if ok else "FAIL", c["expect"], correct, c["why"]))
        if not ok:
            print("       judge said: %s" % reason)
    print("\n%s -- %d of %d fixtures behaved as required."
          % ("USABLE" if not bad else "NOT USABLE", len(SELF_TEST) - bad, len(SELF_TEST)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", nargs="?", help="a results/eval-*.json produced by run.py")
    ap.add_argument("--self-test", action="store_true", help="prove the judge can go red")
    ap.add_argument("--judge-model", default=os.environ.get("JUDGE_MODEL"),
                    help="defaults to MODEL; name it explicitly when judging that same model")
    a = ap.parse_args()

    cfg = config.load()
    if not config.has_key(cfg):
        print("no API_KEY -- the judge needs one. The substring grader in run.py does not, and "
              "still runs offline.")
        return 2
    if a.judge_model:
        cfg = dict(cfg, model=a.judge_model)

    if a.self_test:
        return self_test(cfg)
    if not a.result:
        ap.error("give a results file, or --self-test")

    payload = json.load(open(a.result, encoding="utf-8"))
    labels = {r["id"]: r for r in load_labels()}
    rows = [r for r in payload["rows"] if r.get("answered")]
    if not rows:
        print("%s has no answered rows -- judge it after a run WITH a key." % a.result)
        return 2

    # The model under test is not necessarily the judge. Recording both is what lets a reader see
    # whether a model graded itself, which is a caveat rather than a disqualification.
    judged_by = cfg["model"]
    print("judging %d answers from %s with %s\n" % (len(rows), payload.get("model"), judged_by))

    agree = disagree = unreadable = 0
    for r in rows:
        lab = labels.get(r["id"])
        if not lab:
            continue
        correct, reason = _verdict(cfg, lab["question"], lab["answer"], r.get("answer", ""))
        substring = bool(r.get("correct"))
        r["judge"] = {"correct": correct, "reason": reason, "judged_by": judged_by}
        r["grounded"] = substring          # the old signal, renamed to what it actually measures
        if correct is None:
            unreadable += 1
        elif correct == substring:
            agree += 1
        else:
            disagree += 1
            print("  DISAGREE %-5s substring=%-5s judge=%-5s  %s"
                  % (r["id"], substring, correct, reason))

    readable = [r for r in rows if r["judge"]["correct"] is not None]
    n_correct = sum(r["judge"]["correct"] for r in readable)
    sub_correct = sum(bool(r.get("grounded")) for r in rows)

    s = payload.setdefault("summary", {})
    s["judge_accuracy"] = round(n_correct / len(readable), 4) if readable else None
    s["grounding_rate"] = round(sub_correct / len(rows), 4)
    s["judge_model"] = judged_by
    s["judge_agreement"] = round(agree / (agree + disagree), 4) if (agree + disagree) else None
    s["judge_unreadable"] = unreadable
    # Idempotent: judging a result file twice must not stack duplicate caveats.
    cnv = payload.setdefault("could_not_verify", [])
    cnv[:] = [c for c in cnv if not c.startswith("judge_accuracy is")]
    cnv.append(
        "judge_accuracy is a model's judgement, not ground truth. It never sees answer_contains, "
        "and it was proved red on fluent wrong answers before use (judge.py --self-test), but it "
        "can still be persuaded by a confident wrong answer. grounding_rate is the old exact-"
        "substring signal, kept because it fails in the opposite direction: it cannot be talked "
        "round, and it cannot recognise a paraphrase.")

    print("\n  judged correct   %.1f%%   (%d of %d readable verdicts)"
          % (100 * s["judge_accuracy"], n_correct, len(readable)))
    print("  grounded         %.1f%%   exact fragment present -- NOT a correctness score"
          % (100 * s["grounding_rate"]))
    print("  agreement        %.1f%%   %d agree, %d disagree, %d unreadable"
          % (100 * s["judge_agreement"], agree, disagree, unreadable))

    with open(a.result, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print("\nwrote %s" % os.path.relpath(a.result, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
