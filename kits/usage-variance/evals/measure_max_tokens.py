"""Measure what a reply to THIS prompt actually costs in output tokens, so MAX_TOKENS is a
measurement rather than a number copied off a sibling kit. Spends ONE call.

    python -m evals.measure_max_tokens --run-id c001-usage-variance --doc TLV-0005 --yes

⚑ WHY THIS EXISTS AS ITS OWN STEP. `max_tokens` is the one setting on this call that can silently
change what a run measures: set too low it truncates replies and the harness records them as
documents that "did not parse", which reads as a model failure and is a configuration failure. Set
absurdly high it costs nothing extra on most providers but tells a reader nothing about the shape
of the reply. Both are cheap to avoid and neither is avoidable by reasoning about it -- the only
thing that settles it is one reply and the provider's own usage block.

The call is made at a deliberately oversized ceiling so the reply is NOT clipped, and what is
recorded is what the reply actually used, its finish_reason (which must be "stop", not "length"),
and the provider's completion-token breakdown where it publishes one -- because a reasoning pass
counts against the same ceiling and is invisible in the text.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import adapters, config, extract as EX, prompt as P, segment  # noqa: E402
from src import select as selector                                     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")

CEILING = 8000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--doc", default="TLV-0005")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured — this step needs one live call.")
    if not a.yes and input("this makes 1 live call at max_tokens=%d — type 'run' to continue: "
                           % CEILING).strip() != "run":
        raise SystemExit("nothing was called.")

    fields = EX.load_fields()
    text = EX.load_doc(a.doc)
    secs = segment.sections(text)
    msgs, _parts, _used = P.build(text, secs, fields, selector)
    res = adapters.complete(cfg, msgs[0]["content"], msgs[1]["content"], max_tokens=CEILING)

    out = {
        "run_id": a.run_id,
        "doc": a.doc,
        "model": cfg.get("model"),
        "provider": cfg.get("provider"),
        "ceiling_sent": CEILING,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "reply_chars": len(res.get("text") or ""),
        "note": "One call at an oversized ceiling so the reply is not clipped. finish_reason must "
                "be 'stop'; a 'length' here means even this ceiling was too low and the "
                "measurement is invalid.",
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "calib-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("input_tokens   %s" % out["input_tokens"])
    print("output_tokens  %s" % out["output_tokens"])
    print("finish_reason  %s" % out["finish_reason"])
    print("token_details  %s" % out["token_details"])
    print("reply_chars    %s" % out["reply_chars"])
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
