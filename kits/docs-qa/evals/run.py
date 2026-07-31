"""The eval harness. Scores the labelled set and classifies every failure.

TWO HALVES, AND THE FIRST ONE NEEDS NO KEY.
Retrieval is `pure code`: given the index and the labelled set, whether the passage that answers a
question reached the prompt is decidable offline, for free, deterministically. That half runs on a
fresh clone with no credentials, which is what makes the fork test's "something works in ten
minutes" true rather than aspirational.

The second half calls the model and needs a key. It is the half that costs money and the half
whose numbers expire.

WHY FAILURES ARE CLASSIFIED RATHER THAN COUNTED.
A single accuracy figure tells you the pipeline is wrong and nothing about where. The four causes
below are the taxonomy Foundry's Failure Modes page already publishes, and each one has a
different fix -- and, importantly, a different OWNER:

  not_extracted        the text never survived the file.        Fix: src/extract.py
  dropped_in_chunking  extracted, but no chunk kept it whole.   Fix: src/chunk.py
  bad_ranking          a chunk had it; retrieval ranked it out. Fix: src/retrieve.py
  answered_wrong       it was in the prompt; the answer is not. Fix: src/prompt.py, or the model

Classification is decided by looking, not by guessing: the harness searches the extracted text and
the chunk set for the answer fragment and reports which stage lost it. A taxonomy whose categories
are assigned by a model would be one more thing to verify.

KNOWN DEAD CATEGORY -- `not_extracted` CANNOT FIRE, AND IT IS NOT BECAUSE EXTRACTION IS PERFECT.
check_labels.py verifies that every answer fragment is present in the EXTRACTED text before a
label is allowed into the set. So any label that passes the gate is, by construction, one whose
answer survived extraction, and the one failure the corpus was deliberately built to exhibit is
the one the labelled set can never catch. The gate and the taxonomy are measuring the same text,
which makes that category decoration rather than evidence.

Naming it is the cheap half. Fixing it means labelling against the SOURCE document rather than the
extracted text, so a label can outlive its own pipeline -- a real change to how labels are
authored, not a threshold to tune. Until then this belongs in `could_not_verify`, and any
published extraction claim has to say so.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import _norm, corpus_text, load_labels        # noqa: E402
from src import config, index as ix, prompt as pr, retrieve as rt     # noqa: E402

RESULTS = os.path.join(HERE, "results")


def _present(fragments, text):
    t = _norm(text)
    return all(_norm(f) in t for f in fragments)


def classify(row, hits, index, docs):
    """Where did the answer get lost? Answered by inspection of each stage's own output."""
    frags = row["answer_contains"]
    if _present(frags, " ".join(h["text"] for h in hits)):
        return None
    doc_chunks = [c for c in index["chunks"] if c["doc"] == row["doc"]]
    if not _present(frags, docs.get(row["doc"], "")):
        return "not_extracted"
    if not any(_present(frags, c["text"]) for c in doc_chunks):
        return "dropped_in_chunking"
    return "bad_ranking"


def retrieval_pass(rows, index, docs, k):
    out = []
    for row in rows:
        t0 = time.time()
        mode, hits = rt.retrieve(row["question"], index, k=k)
        ms = (time.time() - t0) * 1000
        cause = classify(row, hits, index, docs)
        out.append({"id": row["id"], "doc": row["doc"], "question": row["question"],
                    "retriever": mode, "latency_ms": round(ms, 2),
                    "top_docs": [h["doc"] for h in hits],
                    "doc_hit": row["doc"] in [h["doc"] for h in hits],
                    "answer_in_context": cause is None, "cause": cause,
                    "hits": [{"id": h["id"], "doc": h["doc"], "format": h["format"],
                              "score": h["score"]} for h in hits]})
    return out


def answer_pass(rows, index, results, cfg, k, limit=None):
    """Needs a key. Adds the model's answer and whether the expected content is in it."""
    from src.adapters import complete
    by_id = {r["id"]: r for r in results}
    for row in rows[:limit] if limit else rows:
        _, hits = rt.retrieve(row["question"], index, k=k)
        system, user, parts = pr.assemble(row["question"], hits)
        t0 = time.time()
        got = complete(cfg, system, user)
        ms = (time.time() - t0) * 1000
        r = by_id[row["id"]]
        correct = _present(row["answer_contains"], got["text"])
        r.update({"answered": True, "model_latency_ms": round(ms, 2),
                  "answer": got["text"], "correct": correct,
                  "input_tokens": got["input_tokens"], "output_tokens": got["output_tokens"],
                  "prompt_chars": len(user), "prompt_parts": len(parts)})
        # A wrong answer whose evidence WAS in the prompt is a different defect from one whose
        # evidence never arrived, and only this order of checks can tell them apart.
        if not correct and r["answer_in_context"]:
            r["cause"] = "answered_wrong"
    return results


def summarise(results, k):
    n = len(results)
    answered = [r for r in results if r.get("answered")]
    lat = sorted(r["latency_ms"] for r in results)
    causes = {}
    for r in results:
        if r["cause"]:
            causes[r["cause"]] = causes.get(r["cause"], 0) + 1
    s = {"rows": n, "top_k": k,
         "doc_hit_rate": round(sum(r["doc_hit"] for r in results) / n, 4),
         "answer_in_context_rate": round(sum(r["answer_in_context"] for r in results) / n, 4),
         "retrieval_latency_p50_ms": lat[n // 2],
         "retrieval_latency_p95_ms": lat[min(n - 1, int(n * 0.95))],
         "causes": causes, "answered": len(answered)}
    if answered:
        mlat = sorted(r["model_latency_ms"] for r in answered)
        s.update({"accuracy": round(sum(r["correct"] for r in answered) / len(answered), 4),
                  "model_latency_p50_ms": mlat[len(mlat) // 2],
                  "model_latency_p95_ms": mlat[min(len(mlat) - 1, int(len(mlat) * 0.95))],
                  "input_tokens_total": sum(r["input_tokens"] or 0 for r in answered),
                  "output_tokens_total": sum(r["output_tokens"] or 0 for r in answered)})
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=rt.TOP_K)
    ap.add_argument("--limit", type=int, default=None, help="cap the model half while iterating")
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--run-id", default=None, help="stamped into the result file")
    a = ap.parse_args()

    rows, index = load_labels(), ix.load()
    docs, _ = corpus_text()
    results = retrieval_pass(rows, index, docs, a.k)

    cfg = config.load()
    ran_model = False
    if not a.retrieval_only and config.has_key(cfg):
        results = answer_pass(rows, index, results, cfg, a.k, a.limit)
        ran_model = True
    elif not a.retrieval_only:
        print("no API_KEY -- retrieval scored, model half skipped. This is the offline path.\n")

    s = summarise(results, a.k)
    print("retrieval: %d rows, k=%d, retriever=%s" % (s["rows"], a.k, results[0]["retriever"]))
    print("  doc in top-k          %.1f%%" % (100 * s["doc_hit_rate"]))
    print("  answer in the prompt  %.1f%%" % (100 * s["answer_in_context_rate"]))
    print("  latency p50 %.2f ms   p95 %.2f ms"
          % (s["retrieval_latency_p50_ms"], s["retrieval_latency_p95_ms"]))
    print("  NOT MEASURED: not_extracted cannot fire -- labels are verified against the same")
    print("  extracted text the taxonomy inspects. See the module docstring.")
    if s["causes"]:
        print("\n  failures by cause -- recorded, not hidden:")
        for c, n in sorted(s["causes"].items(), key=lambda x: -x[1]):
            ids = [r["id"] for r in results if r["cause"] == c]
            print("    %-20s %2d   %s" % (c, n, " ".join(ids[:12])))
    if ran_model:
        print("\nmodel: %s / %s" % (cfg["provider"], cfg["model"]))
        print("  accuracy %.1f%%   p50 %.0f ms   p95 %.0f ms   tokens in/out %d/%d"
              % (100 * s["accuracy"], s["model_latency_p50_ms"], s["model_latency_p95_ms"],
                 s["input_tokens_total"], s["output_tokens_total"]))

    os.makedirs(RESULTS, exist_ok=True)
    run_id = a.run_id or "retrieval-only"
    payload = {"run_id": run_id, "top_k": a.k,
               "retriever": results[0]["retriever"],
               "model": cfg["model"] if ran_model else None,
               "provider": cfg["provider"] if ran_model else None,
               "dataset": {"rows": len(rows), "file": "data/labelled.jsonl"},
               "corpus": {"documents": index["documents"], "chunks": len(index["chunks"]),
                          "by_format": index["by_format"]},
               "summary": s, "rows": results,
               "could_not_verify": [
                   "not_extracted: unreachable by construction -- check_labels.py verifies every "
                   "answer fragment against the extracted text, so no label can describe content "
                   "extraction lost. Testing that needs labels authored against the source "
                   "document rather than the pipeline's own output.",
                   "answered_wrong is unpopulated on a retrieval-only run: it needs the model half."
               ]}
    out = os.path.join(RESULTS, "eval-%s.json" % re.sub(r"[^a-z0-9._-]+", "-", run_id.lower()))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print("\nwrote %s" % os.path.relpath(out, HERE))
    # No as_of / verified_by stamped here: those are provenance the CAPTURE step owns, and a
    # harness that stamps its own provenance is a harness that can stamp a run nobody made.
    return 0


if __name__ == "__main__":
    sys.exit(main())
