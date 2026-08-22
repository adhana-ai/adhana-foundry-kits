#!/usr/bin/env python3
"""Capture ONE real adjudication verbatim, for the report's Prompt lens. SPENDS ONE CALL.

    python3 tools/capture_example.py --doc WCL-0047 --yes

⚑ WHY A SEPARATE CALL RATHER THAN A ROW OUT OF THE EVAL RUN. `evals/run.py` records the first
reply's raw text and nothing else -- it is a scoring harness, not an evidence capture, and the
first claim in a sorted corpus is whichever one sorts first, not the one worth printing. This
writes the whole exchange for a claim chosen on purpose: the prompt as assembled, the reply before
any parsing, the provider's own token counts and finish reason, and the parsed fields beside them.

The published page quotes this file. A raw reply with no note is an artifact; one that names the
claim, the model and the call it came from is evidence.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="WCL-0047")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured.")
    if a.doc not in EX.documents():
        raise SystemExit("no such claim: %s" % a.doc)

    print(BUDGET.plan(1, cfg.get("model")) + " via %s" % cfg.get("provider"))
    if not a.yes and input("type 'run' to continue: ").strip() != "run":
        raise SystemExit("nothing was called.")

    r = EX.extract(cfg, EX.load_doc(a.doc), EX.load_fields())
    out = {
        "doc": a.doc,
        "model": cfg.get("model"),
        "input_tokens": r.get("input_tokens"),
        "output_tokens": r.get("output_tokens"),
        "token_details": r.get("token_details"),
        "finish_reason": r.get("finish_reason"),
        "raw_text": r.get("raw_text"),
        "prompt_parts": r.get("prompt_parts"),
        "sections_used": r.get("sections_used"),
        "fields": {k: v["value"] for k, v in r["fields"].items()},
        "needs_review": r.get("needs_review"),
        "recomputed_covered": r.get("recomputed_covered"),
        "recomputed_months": r.get("recomputed_months"),
        "max_tokens": EX.MAX_TOKENS,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "example-%s.json" % a.doc)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("  in=%s out=%s finish=%s covered=%s needs_review=%s"
          % (out["input_tokens"], out["output_tokens"], out["finish_reason"],
             out["fields"].get("covered"), out["needs_review"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
