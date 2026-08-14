#!/usr/bin/env python3
"""The model run. One call per change request.

    python3 evals/run.py --probe 3 --no-thinking   # 3 calls, proves the shape before the money
    python3 evals/run.py --no-thinking             # 60 calls

⚑ PROBE FIRST. Standing rule, paid for on this estate more than once: measure the fix before buying
it. The probe proves the parse, the record shape and the ingest branch before the other 57 are
spent. A shape you have not tested is a shape that fails at the most expensive moment.

⚑ REASONING OFF BY DEFAULT ON THE FLAG, AND FOR A MEASURED REASON. The sibling kit docs-messy lost
9 of 60 calls to `finish_reason: length` with an EMPTY body when the provider's reasoning pass was
enabled — billed in full, yielding nothing. Reasoning on and reasoning off are two systems, so the
setting rides on the record and the board guards on it.

⚠︎ THE OUTPUT CEILING MATTERS MORE HERE THAN ANYWHERE ELSE IN THIS REPO. The reply is a WHOLE
DOCUMENT, so a ceiling that bites does not truncate a field — it truncates the artifact, and a
truncated document would score as catastrophic collateral damage rather than as the transport
failure it is. `finish_reason` is recorded on every failure so the two can never be confused.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from src import adapters, config, prompt as P  # noqa: E402
from evals.score import score_all, load_requests, load_doc  # noqa: E402

MAX_TOKENS = 1500   # a whole policy document is ~450 tokens; the headroom is deliberate.

BEGIN, END = "---BEGIN DOCUMENT---", "---END DOCUMENT---"


def parse(text):
    """Reply -> (produced_document or None, decision). Raises when the contract was not followed.

    ⚑ A MALFORMED REPLY IS A FAILURE, NOT A REFUSAL. Scoring it as "declined to write" would put it
    in the refusal column and quietly IMPROVE the refusal rate — the run would be rewarded for
    breaking, which is the same trap the sibling kit documents for empty extractions.
    """
    t = (text or "").strip()
    m = re.search(r"DECISION:\s*(APPLY|REFUSE)", t, re.I)
    if not m:
        raise ValueError("no DECISION line")
    decision = m.group(1).upper()
    if decision == "REFUSE":
        return None, "REFUSE"
    if BEGIN not in t or END not in t:
        raise ValueError("APPLY without document sentinels")
    body = t.split(BEGIN, 1)[1].split(END, 1)[0]
    return body.strip("\n"), "APPLY"


def main(argv):
    probe = int(argv[argv.index("--probe") + 1]) if "--probe" in argv else 0
    thinking = adapters.THINKING_OFF if "--no-thinking" in argv else None

    cfg = config.load()
    if not config.has_key(cfg):
        sys.exit("no API_KEY configured — the model half cannot run. The free floor still can: "
                 "python3 evals/baseline.py")

    rows = load_requests(HERE)
    rows = rows[:probe] if probe else rows

    produced, failures, lat = {}, [], []
    tin = tout = 0
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        before = load_doc(HERE, "corpus", r["doc_id"])
        user = P.build(r["request"], before)
        s = time.time()
        try:
            resp = adapters.complete(cfg, P.SYSTEM, user, max_tokens=MAX_TOKENS, thinking=thinking)
        except Exception as e:                                    # noqa: BLE001
            failures.append({"doc_id": r["doc_id"], "why": "call failed: %s" % e})
            continue
        lat.append(int((time.time() - s) * 1000))
        tin += resp.get("input_tokens") or 0
        tout += resp.get("output_tokens") or 0
        try:
            doc, decision = parse(resp["text"])
            produced[r["doc_id"]] = doc
            mark = decision
        except Exception as e:                                    # noqa: BLE001
            # ⚑ KEEP WHAT THE WIRE SAID. Diagnosing a truncated document from a discarded body
            # costs a second run, which on a run-once kit means spending the whole budget again.
            failures.append({"doc_id": r["doc_id"], "why": "unparseable: %s" % e,
                             "finish_reason": resp.get("finish_reason"),
                             # ⚠︎ NOT TRUNCATED TO 600 LIKE THE SIBLING KITS. Their payload is a
                             # short record; this one is a WHOLE DOCUMENT, and 600 characters
                             # cannot tell you whether the body was complete or cut off — which
                             # is the only question a failure here raises. Keeping what the wire
                             # said means keeping enough of it to diagnose.
                             "raw_text": (resp.get("text") or "")[:6000],
                             "raw_len": len(resp.get("text") or "")})
            mark = "FAILED"
        print("  %3d/%d %s %s" % (i, len(rows), r["doc_id"], mark), flush=True)

    answered = [r for r in rows if r["doc_id"] in produced]
    res = score_all(answered, produced, HERE)
    res.update({
        "run_id": ("probe" if probe else "r001-docs-apply-flash"),
        "stub": False, "model": cfg["model"], "provider": cfg["provider"],
        "documents": len(rows), "answered": len(answered),
        "failures": failures, "thinking": thinking,
        "latency_p50_ms": sorted(lat)[len(lat) // 2] if lat else None,
        "latency_p95_ms": sorted(lat)[min(len(lat) - 1, int(len(lat) * .95))] if lat else None,
        "wall_seconds": round(time.time() - t0, 2),
        "input_tokens_total": tin, "output_tokens_total": tout,
    })
    out = os.path.join(HERE, "results", "eval-%s.json" % res["run_id"])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    sc = res["scores"]
    fmt = lambda v: "n/d" if v is None else "%.1f%%" % (100 * v)                  # noqa: E731
    print("\n%s  %d/%d answered  applied %s  clean %s  collateral %d line(s)  "
          "refusal %s  unsafe writes %d  failures %d"
          % (res["run_id"], len(answered), len(rows), fmt(sc["edit_applied"]),
             fmt(sc["edit_clean"]), sc["collateral_lines"], fmt(sc["refusal_accuracy"]),
             sc["unsafe_writes"], len(failures)))
    for fam, v in res["by_family"].items():
        print("   %-14s %d/%d = %.1f%%" % (fam, v["correct"], v["n"], v["pct"]))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
