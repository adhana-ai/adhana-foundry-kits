"""MEASURE the output ceiling this kit needs. Spends a handful of calls at a generous cap.

    python -m evals.max_tokens --run-id c000-commission-audit --n 3 --ceiling 8000 --yes

⚠︎ `MAX_TOKENS` IN src/extract.py IS A MEASUREMENT, NOT A GUESS, AND THIS IS THE FILE THAT MAKES
IT ONE. A ceiling copied from a sibling kit is a guess wearing a sibling's evidence: this kit's
record carries fourteen fields, two of them free text copied back verbatim, and nothing about
another kit's ten-field record says what that costs.

The method is the smallest honest one. Fire `--n` records at a ceiling far above anything the
shape could plausibly need, read the provider's OWN `output_tokens` and `finish_reason` back, and
record both. A reply that stops on "stop" spent what it wanted to spend; a reply that stops on
"length" at the ceiling did not, and the measurement is void. The committed file is the evidence
the constant is set against.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import adapters, config, extract as EX, prompt as P    # noqa: E402
from src import segment, select as selector                     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--ceiling", type=int, default=8000)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured — this measurement needs one.")
    fields = EX.load_fields()
    docs = EX.documents()[:a.n]
    if not a.yes and input("this measures %d call(s) at max_tokens=%d — type 'run' to continue: "
                           % (len(docs), a.ceiling)).strip() != "run":
        raise SystemExit("nothing was called.")

    rows = []
    for claim_ref in docs:
        text = EX.load_doc(claim_ref)
        secs = segment.sections(text)
        msgs, _parts, _used = P.build(text, secs, fields, selector)
        res = adapters.complete(cfg, msgs[0]["content"], msgs[1]["content"],
                                max_tokens=a.ceiling)
        parsed = P.parse(res.get("text", ""), fields)
        rows.append({"doc": claim_ref,
                     "input_tokens": res.get("input_tokens"),
                     "output_tokens": res.get("output_tokens"),
                     "finish_reason": res.get("finish_reason"),
                     "token_details": res.get("token_details"),
                     "parsed_keys": sum(1 for v in parsed.values() if v is not None)})
        print("  %-10s %5d in  %5d out  finish=%s  %d field(s) parsed"
              % (claim_ref, rows[-1]["input_tokens"] or 0, rows[-1]["output_tokens"] or 0,
                 rows[-1]["finish_reason"], rows[-1]["parsed_keys"]))

    largest = max((r["output_tokens"] or 0) for r in rows)
    clipped = [r["doc"] for r in rows if r["finish_reason"] == "length"]
    out = {"run_id": a.run_id, "ceiling_measured_at": a.ceiling, "calls": len(rows),
           "rows": rows, "largest_output_tokens": largest,
           "clipped_at_ceiling": clipped,
           "note": ("Every reply stopped on its own; the largest spent %d of the %d-token ceiling, "
                    "so the measurement is a real ceiling requirement rather than a truncation."
                    % (largest, a.ceiling)) if not clipped else
                   ("%d reply(s) stopped at the ceiling — this measurement is VOID, re-run it "
                    "higher." % len(clipped))}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "tokens-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("\nlargest output: %d tokens of a %d ceiling; clipped: %s"
          % (largest, a.ceiling, clipped or "none"))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
