#!/usr/bin/env python3
"""Capture one reply VERBATIM, for the LLM lens's `raw_response`. SPENDS ONE CALL.

    python3 tools/capture_example.py --doc LBL-0032 --yes

⚑ WHY A FRESH CALL RATHER THAN A REPLY FROM THE SCORED RUN. evals/run.py records only the FIRST
case's raw text, because storing 52 full replies in every result file makes the run record
unreadable for a figure only one of them is ever used for. So the worked example is re-asked, once,
and committed on its own -- and the file says which run it sits beside, so nobody can quote it as
though it were a 53rd scored case.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, extract as EX          # noqa: E402
from src import segment, select as selector, prompt as P   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="LBL-0032")
    ap.add_argument("--beside", default="r001-label-restrict")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured.")
    if not a.yes and input("this spends ONE call — type 'run' to continue: ").strip() != "run":
        raise SystemExit("nothing was called.")

    fields = EX.load_fields()
    text = EX.load_doc(a.doc)
    r = EX.extract(cfg, text, fields)

    secs = segment.sections(text)
    _msgs, parts, used = P.build(text, secs, fields, selector)

    out = {
        "doc": a.doc,
        "beside_run": a.beside,
        "note": ("A fresh single call replayed after the scored run, to capture one reply "
                 "verbatim. It is NOT a 53rd scored case and is not counted in any denominator."),
        "model": cfg.get("model"),
        "provider": cfg.get("provider"),
        "max_tokens": EX.MAX_TOKENS,
        "input_tokens": r.get("input_tokens"),
        "output_tokens": r.get("output_tokens"),
        "finish_reason": r.get("finish_reason"),
        "token_details": r.get("token_details"),
        "raw_text": r.get("raw_text"),
        "sections_used": used,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])} for q in parts],
        "values": {k: v["value"] for k, v in r["fields"].items()},
        "spans": {k: (v["span"]["section"] if v["span"] else None) for k, v in r["fields"].items()},
        "needs_hold": r.get("needs_hold"),
        "recomputed_verdict": r.get("recomputed_verdict"),
        "recomputed_restriction": r.get("recomputed_restriction"),
        "recomputed_reason": r.get("recomputed_reason"),
        "recomputed_checks": r.get("recomputed_checks"),
        "document_text": text,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "example-%s.json" % a.doc)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(r.get("raw_text"))
    print("\ninput %s  output %s  finish %s" % (out["input_tokens"], out["output_tokens"],
                                                out["finish_reason"]))
    print("needs_hold %r   recomputed %r / %r"
          % (out["needs_hold"], out["recomputed_verdict"], out["recomputed_restriction"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
