#!/usr/bin/env python3
"""The model run. One call per document, one condition per invocation.

    python3 evals/run.py --probe 3 clean     # three calls, to prove the shape before the money
    python3 evals/run.py clean               # 60 calls
    python3 evals/run.py messy               # 60 calls

⚑ ONE CONDITION PER INVOCATION, AND THE CONDITION IS A GUARD ON THE RECORD. A clean run and a
messy run are not two attempts at the same thing — they are two systems, and the board must refuse
to difference them as though one improved on the other. That is what `condition` in guards buys.

⚑ PROBE FIRST. Standing rule, paid for on this estate more than once: measure the fix before
buying it. `--probe 3` spends three calls and proves the parse, the record shape and the ingest
branch before the other 117 are spent. A shape you have not tested is a shape that fails at the
most expensive moment.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from src import adapters, config, prompt as P  # noqa: E402
from evals.score import score_all, load_gold, load_fields  # noqa: E402

MAX_TOKENS = 700   # a six-field JSON record. Recorded with finish_reason so truncation is visible.


def parse(text):
    """Model text -> dict. Tolerates a code fence; refuses to guess at anything else.

    ⚑ A PARSE FAILURE IS RECORDED AS A FAILURE, NOT AS AN EMPTY EXTRACTION. An unparseable reply
    scored as "returned nothing" would land in the refusal column and quietly IMPROVE the refusal
    rate — the run would be rewarded for breaking.
    """
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    return json.loads(m.group(0))


def main(argv):
    condition = "messy" if "messy" in argv else "clean"
    probe = 0
    if "--probe" in argv:
        probe = int(argv[argv.index("--probe") + 1])

    # ⚑ REASONING OFF, AND MEASURED BEFORE IT WAS ADOPTED — 2026-08-14.
    #
    # The first clean run lost NINE of sixty calls. Every one of them came back
    # `finish_reason: length` with an EMPTY text body: the whole 700-token budget went to reasoning
    # tokens this task does not need, and none of it was returned. That is the most expensive
    # outcome a call has — billed in full, yields nothing — and the sibling kits document the same
    # provider behaviour.
    #
    # ⚠︎ AND IT WAS NOT ONLY A COST PROBLEM. Losing a DIFFERENT number of documents in each
    # condition would leave the two halves covering different document sets, and the gap between
    # them is this kit's entire result. A contaminated denominator is worse than an expensive run.
    #
    # Reasoning on and reasoning off are two systems, so this rides in `thinking` on the record and
    # the board guards on it — a run made with it cannot be differenced against one made without.
    thinking = adapters.THINKING_OFF if "--no-thinking" in argv else None

    cfg = config.load()
    if not config.has_key(cfg):
        sys.exit("no API_KEY configured — the model half cannot run. The free floor still can: "
                 "python3 evals/baseline.py %s" % condition)

    gold = load_gold(HERE)
    fields_full = json.load(open(os.path.join(HERE, "data", "fields.json"),
                                 encoding="utf-8"))["fields"]
    fields = [f["key"] for f in fields_full]
    rows = gold[:probe] if probe else gold

    preds, failures, lat = {}, [], []
    tin = tout = 0
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        doc = open(os.path.join(HERE, "data", "corpus", condition, row["doc_id"] + ".txt"),
                   encoding="utf-8").read()
        user = P.build(fields_full, doc)
        s = time.time()
        try:
            r = adapters.complete(cfg, P.SYSTEM, user, max_tokens=MAX_TOKENS, thinking=thinking)
        except Exception as e:                                    # noqa: BLE001
            failures.append({"doc_id": row["doc_id"], "why": "call failed: %s" % e})
            continue
        lat.append(int((time.time() - s) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        try:
            preds[row["doc_id"]] = parse(r["text"])
        except Exception as e:                                    # noqa: BLE001
            # ⚑ KEEP WHAT THE WIRE SAID. Diagnosing a truncation from a discarded body costs a
            # second run, which on a run-once kit means spending the whole budget again.
            failures.append({"doc_id": row["doc_id"], "why": "unparseable: %s" % e,
                             "finish_reason": r.get("finish_reason"),
                             "raw_text": (r.get("text") or "")[:600]})
        print("  %3d/%d %s %s" % (i, len(rows), row["doc_id"],
                                  "ok" if row["doc_id"] in preds else "FAILED"), flush=True)

    # ⚑ RATES ARE OVER THE DOCUMENTS THAT ANSWERED, AND `answered` SHIPS BESIDE THEM.
    # Scoring a dead call as six wrong cells conflates "the model misread the page" with "the
    # model never replied" — two different defects with two different fixes, and only one of them
    # is about legibility, which is the thing this kit measures. The attempted count, the answered
    # count and the failure list are all on the record, so nobody has to infer the denominator.
    answered = [g for g in rows if g["doc_id"] in preds]
    res = score_all(answered, preds, fields)
    res.update({
        "run_id": ("probe-%s" % condition) if probe else
                  ("r001-%s" % condition if condition == "clean" else "r002-%s" % condition),
        "stub": False, "model": cfg["model"], "provider": cfg["provider"],
        "condition": condition, "documents": len(rows), "answered": len(answered),
        "failures": failures, "thinking": thinking,
        "latency_p50_ms": sorted(lat)[len(lat) // 2] if lat else None,
        "latency_p95_ms": sorted(lat)[min(len(lat) - 1, int(len(lat) * .95))] if lat else None,
        "wall_seconds": round(time.time() - t0, 2),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "prompt_parts": [{"name": p["name"], "chars": len(p["text"])}
                         for p in P.parts(fields_full, "")],
    })
    out = os.path.join(HERE, "results", "eval-%s.json" % res["run_id"])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    sc = res["scores"]
    print("\n%s  %s  %d doc(s)  accuracy %s  refusal %s  hallucinations %d  failures %d"
          % (res["run_id"], condition, len(rows),
             "%.1f%%" % (100 * sc["extraction_accuracy"]) if sc["extraction_accuracy"] is not None else "n/d",
             "%.1f%%" % (100 * sc["refusal_accuracy"]) if sc["refusal_accuracy"] is not None else "n/d",
             sc["hallucinations"], len(failures)))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
