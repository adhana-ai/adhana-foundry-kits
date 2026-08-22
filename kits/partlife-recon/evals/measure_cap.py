"""Measure what MAX_TOKENS actually needs to be, before a scored run is allowed to depend on it.

    python -m evals.measure_cap --run-id c001-<kit> --n 3 --ceiling 6000 --yes

⚑ WHY THIS FILE EXISTS. `MAX_TOKENS` decides whether a reply arrives whole or truncated, and a
truncated reply fails to parse and is recorded as a FAILED DOCUMENT -- which reads on a results
page as a model that could not do the task, when it is a ceiling the author guessed at. Several
sibling kits in this series set the ceiling by copying the previous kit's number, and one of them
spent a whole paid run discovering that its nine-field record ran to exactly the cap on four
documents. A ceiling is a MEASUREMENT of this prompt on this corpus, and three calls buy it.

It sends real packs at a deliberately generous ceiling and records what came back: the output token
count the provider itself reports, and its own `finish_reason`. A run where every reply finished on
`stop` has measured the reply length; a run where anything finished on `length` has measured the
ceiling instead and has to be repeated higher.

The packs are chosen as the LONGEST in the corpus rather than at random -- the reply carries the
reviewer's note back verbatim and the pack with the most trail lines is the one whose reply is
biggest, so a sample of typical packs would under-measure exactly the case that truncates.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--ceiling", type=int, default=6000)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    fields = EX.load_fields()
    docs = sorted(EX.documents(), key=lambda d: -len(EX.load_doc(d)))[:a.n]

    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured.")
    if not a.yes and input("this measures %d call(s) at max_tokens=%d — type 'run' to continue: "
                           % (len(docs), a.ceiling)).strip() != "run":
        raise SystemExit("nothing was called.")

    obs = []
    for rec_id in docs:
        text = EX.load_doc(rec_id)
        secs = segment.sections(text)
        msgs, _parts, _used = P.build(text, secs, fields, selector)
        res = adapters.complete(cfg, msgs[0]["content"], msgs[1]["content"],
                                max_tokens=a.ceiling)
        parsed = P.parse(res.get("text", ""), fields)
        row = {"doc": rec_id, "doc_chars": len(text),
               "input_tokens": res.get("input_tokens"),
               "output_tokens": res.get("output_tokens"),
               "finish_reason": res.get("finish_reason"),
               "token_details": res.get("token_details"),
               "reply_chars": len(res.get("text") or ""),
               "parsed": bool(parsed) and any(v is not None for v in parsed.values())}
        obs.append(row)
        print("  %-10s %5s output tokens  finish_reason=%s  parsed=%s"
              % (rec_id, row["output_tokens"], row["finish_reason"], row["parsed"]))

    outs = [o["output_tokens"] or 0 for o in obs]
    hi = max(outs) if outs else 0
    truncated = [o["doc"] for o in obs if o["finish_reason"] == "length"]
    out = {
        "run_id": a.run_id,
        "kind": "cap-measurement",
        "model": cfg.get("model"),
        "ceiling_probed": a.ceiling,
        "documents": len(obs),
        "chosen": "the %d longest packs in the corpus, by character count" % len(obs),
        "observations": obs,
        "output_tokens_max": hi,
        "output_tokens_min": min(outs) if outs else None,
        "any_truncated": bool(truncated),
        "truncated": truncated,
        "note": ("Every reply finished on `stop`, so this measured the REPLY, not the ceiling."
                 if not truncated else
                 "At least one reply finished on `length`, so this measured the CEILING and the "
                 "probe must be repeated higher before MAX_TOKENS is set from it."),
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "cap-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("\nlongest reply: %d output tokens; truncated: %s" % (hi, truncated or "none"))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
