"""Measure the prompt split in TOKENS, not characters. Spends a few calls at max_tokens=1.

    python -m evals.prompt_tokens --run-id p001 --doc UTL-0001

No local tokenizer here -- stdlib only. The prompt is sent as nested prefixes, each the previous
plus exactly one more part; each part's size is the difference between two consecutive
`prompt_tokens` counts the provider itself returns.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, extract as EX, prompt as P, segment, select as selector  # noqa: E402
from src import adapters                                                         # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def prefixes(doc_text, fields):
    secs = segment.sections(doc_text)
    msgs, parts, _ = P.build(doc_text, secs, fields, selector)
    system, full_user = msgs[0]["content"], msgs[1]["content"]
    schema = P.field_schema(fields)
    a = "Extract these fields:\n%s\n\n" % schema
    assert full_user.startswith(a), "prompt shape changed — this measurement would be wrong"
    return system, [("", "chat protocol and system prompt"),
                    (a, "field schema"),
                    (full_user, "record sections")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--doc", default="UTL-0001")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    fields = EX.load_fields()
    text = EX.load_doc(a.doc)
    system, steps = prefixes(text, fields)

    if not a.yes and input("this measures %d calls at max_tokens=1 — type 'run' to continue: "
                           % len(steps)).strip() != "run":
        raise SystemExit("nothing was called.")

    counts, labels = [], []
    for user, label in steps:
        res = adapters.complete(cfg, system, user or " ", max_tokens=1)
        counts.append(res.get("input_tokens") or 0)
        labels.append(label)
        print("  %-32s %6d prompt_tokens (cumulative)" % (label, counts[-1]))

    parts = []
    for i, label in enumerate(labels):
        prev = counts[i - 1] if i else 0
        parts.append({"label": label, "tokens": counts[i] - prev})

    out = {"run_id": a.run_id, "doc": a.doc, "cumulative": list(zip(labels, counts)),
          "parts": parts, "total": counts[-1]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "tokens-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("\nparts:")
    for p in parts:
        print("  %-32s %6d tokens" % (p["label"], p["tokens"]))
    print("total: %d" % counts[-1])
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
