#!/usr/bin/env python3
"""Measure the prompt split in TOKENS, not characters. Two calls at max_tokens=1.

    python3 evals/prompt_tokens.py d000        # 2 calls

⚑ WHY NOT CHARACTERS. `run.py` records `prompt_parts` as `[{name, chars}]`, and the Cost lens
publishes that split as a share of the bill. Characters are a proxy for tokens and not a uniform
one — the instruction block is dense punctuation and short type names, the document is ordinary
prose with columns of digits, and those tokenize at visibly different characters-per-token. A split
published in characters reports a share of a bill nobody is billed for.

⚑ IT IS A SUBTRACTION, AND THE PROVIDER'S OWN TOKENIZER DOES THE COUNTING. There is no local
tokenizer here: this kit is standard library only, and shipping a vendor's would be wrong for every
other provider the adapter supports. What every provider DOES return is `prompt_tokens` for the
prompt it was actually billed for. So the prompt is sent twice — once as the instruction block
alone, once whole — and the document's share is the difference.

⚠︎ A TOKEN MAY SPAN THE BOUNDARY between the two parts, so a part's count can be off by one against
a tokenizer run on that part in isolation. That is not an error to correct: the parts are never
sent in isolation, and the boundary token really is billed once. The published figure is "what this
part adds to the bill".
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from src import adapters, config, prompt as P  # noqa: E402


def main(doc_id="d000"):
    cfg = config.load()
    if not config.has_key(cfg):
        sys.exit("no API_KEY configured")
    fields = json.load(open(os.path.join(HERE, "data", "fields.json"),
                            encoding="utf-8"))["fields"]
    doc = open(os.path.join(HERE, "data", "corpus", "clean", doc_id + ".txt"),
               encoding="utf-8").read()

    head = P.build(fields, "")          # the instruction block with an empty document
    whole = P.build(fields, doc)

    a = adapters.complete(cfg, P.SYSTEM, head, max_tokens=1,
                          thinking=adapters.THINKING_OFF)["input_tokens"]
    b = adapters.complete(cfg, P.SYSTEM, whole, max_tokens=1,
                          thinking=adapters.THINKING_OFF)["input_tokens"]

    out = {
        "doc_id": doc_id, "method": "prefix subtraction, provider tokenizer, 2 calls",
        "input_tokens_total": b,
        "parts": [
            {"name": "instruction and field shape", "tokens": a},
            {"name": "the document", "tokens": b - a},
        ],
    }
    p = os.path.join(HERE, "results", "prompt-tokens.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print(json.dumps(out, indent=1))
    print("wrote %s" % p)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "d000")
