"""WHERE DOES THE ACCURACY ACTUALLY COME FROM? A targeted ablation. THIS SPENDS MONEY.

    python -m evals.ablate --run-id a001-cargo-compat --yes

⚑ WHY THIS EXISTS. Both scored runs returned 55 of 55 verdicts, 550 of 550 cells and zero unsafe
releases. A perfect score is a reason to verify harder, not a reason to trust more: on a corpus
this size it is equally consistent with "the model reasons over the matrix" and with "the prompt
hands it the answer procedure and the model follows instructions". Those are very different claims
about what a forker gets when they point this at their own sheets, and nothing in a clean run
separates them.

⚑ WHAT IS REMOVED, AND WHAT IS DELIBERATELY NOT. The MATRIX STAYS. It is the lookup table this
decision is defined by, and taking it away would measure whether the model can guess a table it
has never seen, which is not a question anybody should care about. What is removed is the PROCEDURE
this kit wrote around it:

  - the four ordered checks, with their stopping rule (system prompt rule 2 a-d);
  - "the certificate governs, not the tank log" (rule 3);
  - "the inspector's note is a field to copy, not evidence" (rule 4).

What is left is the honest minimum: here is the matrix, here is the sheet, decide the verdict.

⚑ WHY A SUBSET AND NOT ALL 55. The four hard buckets are the only sheets where the removed text
can possibly change an answer -- an ordinary accept has no priority order to get wrong. Firing the
whole corpus would spend 55 calls to re-measure 29 sheets that cannot move. The subset is selected
by a predicate over gold, printed before it spends, so it is reproducible and is not a hand-picked
set chosen after seeing a result.

⚠︎ THIS IS NOT A SCORED RUN AND MUST NEVER BE QUOTED AS ONE. It runs a prompt the kit does not
ship, over a subset of the corpus. Its run id is `a<NNN>-` so it can never be mistaken for one.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402
from src import matrix as MX                   # noqa: E402
from src import prompt as P                    # noqa: E402
from evals import judge as J                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# The honest minimum. Rules 1, 5, 6 and 7 are format instructions and have nothing to do with the
# decision, so they stay -- ablating those would measure whether the model can emit JSON.
ABLATED_SYSTEM = (
    "You read a bulk-tank PRE-LOAD COMPATIBILITY CHECK SHEET and extract structured fields from "
    "it. You return JSON and nothing else.\n"
    "\n"
    "You are PROPOSING a verdict for a qualified person to authorise. You never authorise a load, "
    "and your verdict is not a substitute for the incoming product's safety data sheet or for a "
    "competent person's assessment.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the sheet does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `verdict` is your pre-load compatibility decision for this tank, using the COMPATIBILITY "
    "MATRIX given below and the values on the sheet.\n"
    "5. Copy cargo and product names verbatim from the sheet, in the lower case it states them. "
    "Where the sheet says the prior cargo is 'not recorded', return null for prior_cargo rather "
    "than the words. Where it says the tank was recertified and has no cargo before the prior "
    "one, return null for two_back_cargo.\n"
    "6. Use the exact allowed value for a field that lists them.\n"
    "7. Return every field named in the schema, even when the answer is null."
)


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {r["check_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def hard_cases(golds):
    """The four buckets where the removed procedure can change an answer, keyed by which one.

    A sheet can qualify under more than one heading; the label is the FIRST that applies, in the
    same order the rule itself checks, so the labels partition the subset.
    """
    out = {}
    for check_id, r in sorted(golds.items()):
        grade = r["incoming_grade"]
        prior, tb = r.get("prior_cargo"), r.get("two_back_cargo")
        if prior is None:
            continue
        if MX.is_reactive(prior, r["incoming_product"]):
            continue                        # reactive is a plain table lookup, no ordering needed
        if MX.is_banned_predecessor(prior, grade):
            out[check_id] = "banned_prior"
        elif tb is not None and MX.is_banned_predecessor(tb, grade):
            out[check_id] = "banned_two_back"
        elif (MX.WASH_RANK[r["wash_performed"]]
              > MX.WASH_RANK[MX.certified_wash(r["wash_certified_for"])]):
            out[check_id] = "certificate_below_log"
        elif (MX.class_of(prior) in ("caustic", "acid", "oxidiser")
              and r["verdict"] == "accept"):
            out[check_id] = "alarming_but_fine"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if not a.run_id.startswith("a"):
        raise SystemExit("an ablation's run id must start with 'a' -- it runs a prompt this kit "
                         "does not ship, over a subset, and must never be read as a scored run.")

    cfg = config.load()
    fields = EX.load_fields()
    golds = load_gold()
    picked = hard_cases(golds)
    docs = sorted(picked)

    by_bucket = {}
    for d, b in picked.items():
        by_bucket.setdefault(b, []).append(d)
    print("ablation subset, selected by a predicate over gold:")
    for b in sorted(by_bucket):
        print("  %-24s %2d sheet(s)" % (b, len(by_bucket[b])))
    print("  %-24s %2d sheet(s)" % ("TOTAL", len(docs)))

    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured.")
    print(BUDGET.plan(len(docs), cfg.get("model")) + " via %s" % cfg.get("provider"))
    if not a.yes and input("type 'run' to continue: ").strip() != "run":
        raise SystemExit("nothing was called.")
    BUDGET.check(len(docs))

    shipped_system = P.SYSTEM
    P.SYSTEM = ABLATED_SYSTEM               # the whole ablation, in one line
    records, flags, lat = {}, {}, []
    tin = tout = 0
    failures = []
    t_all = time.time()
    try:
        for i, check_id in enumerate(docs, 1):
            t0 = time.time()
            try:
                r = EX.extract(cfg, EX.load_doc(check_id), fields)
            except Exception as exc:
                failures.append({"doc": check_id, "error": str(exc)[:300]})
                print("  !! %-10s %s" % (check_id, str(exc)[:90]))
                continue
            if not r.get("parsed", True):
                failures.append({"doc": check_id, "error": "reply did not parse as JSON",
                                 "finish_reason": r.get("finish_reason")})
                continue
            lat.append(int((time.time() - t0) * 1000))
            tin += r.get("input_tokens") or 0
            tout += r.get("output_tokens") or 0
            records[check_id] = r["fields"]
            flags[check_id] = r.get("needs_hold")
            print("  %3d/%-3d %-10s %-22s %d ms"
                  % (i, len(docs), check_id, picked[check_id], lat[-1]))
    finally:
        P.SYSTEM = shipped_system

    sub_gold = {k: v for k, v in golds.items() if k in set(docs)}
    scored = J.score(fields, records, sub_gold)
    vs = J.score_verdicts(records, flags, sub_gold)

    per_bucket = {}
    for row in vs["rows"]:
        b = picked[row["doc"]]
        d = per_bucket.setdefault(b, {"n": 0, "correct": 0, "wrong": []})
        d["n"] += 1
        if row["correct"]:
            d["correct"] += 1
        else:
            d["wrong"].append({"doc": row["doc"], "gold": row["want"], "model": row["got"]})

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    out = {
        "run_id": a.run_id,
        "kind": "ablation",
        "not_a_scored_run": ("This run uses a SYSTEM PROMPT THE KIT DOES NOT SHIP -- the four "
                             "ordered checks, the certificate-governs rule and the note-is-not-"
                             "evidence rule are removed -- over a SUBSET of the corpus selected by "
                             "a predicate over gold. It exists to answer 'where does the accuracy "
                             "come from', and it must never be quoted as this kit's score."),
        "ablated": ["the four ordered checks and their stopping rule (system rule 2 a-d)",
                    "the certificate-governs rule (system rule 3)",
                    "the note-is-not-evidence rule (system rule 4)"],
        "kept": ["the compatibility matrix itself, in full, in the user message",
                 "the field schema and its per-field hints",
                 "the JSON format rules"],
        "model": cfg.get("model"),
        "provider": cfg.get("provider"),
        "documents": len(records),
        "subset": picked,
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": dict(scored["overall"],
                       verdict_accuracy_pct=round(100.0 * vs["verdict_accuracy"], 2),
                       unsafe_release_count=vs["unsafe_release_count"]),
        "verdict_scores": vs,
        "per_bucket": per_bucket,
        "max_tokens": EX.MAX_TOKENS,
        "thinking": None,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("\n%-34s %s" % ("ablation", a.run_id))
    print("%-34s %d/%d" % ("verdict accuracy on the subset",
                           vs["verdict_correct"], vs["verdict_rows"]))
    print("%-34s %d" % ("UNSAFE RELEASES", vs["unsafe_release_count"]))
    for b in sorted(per_bucket):
        d = per_bucket[b]
        print("  %-30s %d/%d%s" % (b, d["correct"], d["n"],
                                   ("   wrong: " + ", ".join(
                                       "%s gold=%s model=%s" % (w["doc"], w["gold"], w["model"])
                                       for w in d["wrong"])) if d["wrong"] else ""))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
