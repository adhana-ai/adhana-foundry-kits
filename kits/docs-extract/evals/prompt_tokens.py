"""Measure the prompt split in TOKENS, not characters. Spends a few calls at max_tokens=1.

    python -m evals.prompt_tokens --run-id p001 --docs 3          # THIS SPENDS MONEY (6 calls)
    python -m evals.prompt_tokens --run-id p000 --docs 2 --stub   # free, proves the wiring

⚠︎ WHY CHARACTERS WERE NOT GOOD ENOUGH. `evals/run.py` records `prompt_parts` as
`[{name, chars}]`, and the Cost lens publishes that split. Characters are a proxy for tokens and
they are not a uniform one: the field schema is dense punctuation and short type names, the
document sections are ordinary English prose, and those two tokenize at visibly different
characters-per-token. A split published in characters therefore reports a share of the bill that
nobody is billed for — and the bill is the entire subject of that lens.

⚑ HOW IT MEASURES, AND WHY IT IS A SUBTRACTION. There is no local tokenizer here: this kit is
standard library only, and shipping a vendor's tokenizer would both add a dependency and be wrong
for every other provider the adapter supports. What every provider DOES return is `prompt_tokens`
for the prompt it was actually billed for. So the prompt is sent as a series of nested prefixes,
each one the previous plus exactly one more part, and each part's size is the difference between
two consecutive counts. That is the provider's own tokenizer measuring its own prompt, which is
the only number that matches an invoice.

⚑ THREE OF THE FOUR PREFIXES ARE THE SAME FOR EVERY DOCUMENT, so they are measured ONCE. The
system prompt and the field schema do not vary by document, and neither does the framing between
the schema and the document text. Only the selected sections change. That makes the cost 3 fixed
calls plus 1 per document sampled, and it also gives the method its own check: if the constant
prefixes did not come back constant, the measurement would be wrong and it would be visible.

⚠︎ WHAT A SUBTRACTION CANNOT SEE. A token may span the boundary between two parts, so a part's
count can be off by one against a hypothetical tokenizer run on that part in isolation. That is
not an error to correct — the parts are never sent in isolation, and the boundary token really is
billed once in the whole prompt. The published figure is "what this part adds to the bill", which
is the question a reader has, and the result file says so in those words.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                                    # noqa: E402
from src import config, extract as EX, prompt as P, segment, select as selector  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def prefixes(doc_text, fields):
    """The four nested prompts, shortest first, each the previous plus one part.

    They are rebuilt from prompt.build's own format string rather than re-typed, so a change to
    the prompt cannot leave this file measuring a shape the kit no longer sends. The full one is
    asserted identical to what build() produces before anything is spent.
    """
    secs = segment.sections(doc_text)
    msgs, parts, _ = P.build(doc_text, secs, fields, selector)
    system, full_user = msgs[0]["content"], msgs[1]["content"]

    schema = P.field_schema(fields)
    names = ", ".join(f["name"] for f in fields)
    a = "Extract these fields:\n%s\n\n" % schema
    b = a + ("Return a JSON object with exactly these keys: %s\n"
             "Use null for any field the document does not state.\n\n"
             "DOCUMENT\n--------\n" % names)
    assert full_user.startswith(b), "prompt shape changed — this measurement would be wrong"
    return system, [("", "chat protocol and system prompt"),
                    (a, "field schema"),
                    (b, "instruction framing"),
                    (full_user, "document sections")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--docs", type=int, default=3)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    fields = EX.load_fields()
    docs = EX.documents()[:a.docs]
    n = 3 + len(docs)                      # 3 constant prefixes + the full prompt per document

    def count(system, user):
        if a.stub:
            return len(system) // 4 + len(user) // 4
        from src import adapters
        return adapters.complete(cfg, system, user or ".", max_tokens=1)["input_tokens"]

    if not a.stub:
        if not config.has_key(cfg):
            raise SystemExit("no API_KEY configured. Use --stub to prove the wiring for free.")
        print(BUDGET.plan(n, cfg.get("model")))
        if not a.yes and input("type 'run' to continue: ").strip() != "run":
            raise SystemExit("nothing was called.")
        BUDGET.check(n)

    system, pre = prefixes(EX.load_doc(docs[0]), fields)
    # The three constant prefixes, measured once. Their labels come from `prefixes` so the result
    # file and the measurement can never disagree about which part is which.
    const = [count(system, pre[i][0]) for i in range(3)]
    rows, per_doc = [], []
    for nct in docs:
        system_d, pre_d = prefixes(EX.load_doc(nct), fields)
        assert [p[0] for p in pre_d[:3]] == [p[0] for p in pre[:3]], "constant prefix is not constant"
        total = count(system_d, pre_d[3][0])
        per_doc.append({"doc": nct, "prompt_tokens": total,
                        "document_sections": total - const[2],
                        # This document's own section text, not doc[0]'s — the sections are the
                        # one part that varies, which is the entire reason a mean is taken.
                        "document_chars": len(pre_d[3][0]) - len(pre_d[2][0])})
        print("  %-14s prompt %5d tokens  (document sections %5d)"
              % (nct, total, total - const[2]))

    doc_tokens = [d["document_sections"] for d in per_doc]
    cuts = [const[0], const[1] - const[0], const[2] - const[1],
            round(sum(doc_tokens) / len(doc_tokens))]
    # ⚠︎ CHARS ARE DELTAS TOO, and the first version published cumulative ones beside delta
    # tokens. The whole point of this file is to compare the two units part by part, and a
    # cumulative figure next to an incremental one makes the schema look four times denser than
    # it is. `pre` holds nested prefixes, so every char figure is a subtraction exactly as every
    # token figure is; the first row is the chat protocol plus the system prompt, whose character
    # count is the system string rather than any prefix of the user message.
    doc_chars = [d["document_chars"] for d in per_doc]
    char_cuts = [len(system), len(pre[1][0]), len(pre[2][0]) - len(pre[1][0]),
                 round(sum(doc_chars) / len(doc_chars))]
    for (txt, label), tok, ch in zip(pre, cuts, char_cuts):
        rows.append({"part": label, "tokens": tok, "chars": ch,
                     "chars_per_token": round(ch / tok, 2) if tok else None})

    total_avg = sum(cuts)
    for r in rows:
        r["share_pct"] = round(100.0 * r["tokens"] / total_avg, 1)

    out = {
        "run_id": a.run_id, "kind": "prompt_tokens", "stub": bool(a.stub),
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "documents": len(docs), "calls": n,
        "parts": rows,
        "per_document": per_doc,
        "prompt_tokens_avg": total_avg,
        "method": "Nested prefixes, each the previous plus one part, sent at max_tokens=1; every "
                  "part's size is the difference between two consecutive prompt_tokens counts as "
                  "the provider reported them. The first three prefixes do not vary by document "
                  "and were measured once; the document-sections figure is the mean over the "
                  "%d documents sampled." % len(docs),
        "caveat": "A token may span the boundary between two parts, so a part's count can differ "
                  "by one from that part tokenized alone. The parts are never sent alone, and the "
                  "figure published is what each part ADDS to the billed prompt.",
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("\n%-34s %8s %8s %7s" % ("part", "tokens", "chars", "share"))
    for r in rows:
        print("  %-32s %8s %8s %6s%%"
              % (r["part"], r["tokens"], r["chars"] if r["chars"] is not None else "-",
                 r["share_pct"]))
    print("  %-32s %8d" % ("TOTAL (average prompt)", total_avg))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
