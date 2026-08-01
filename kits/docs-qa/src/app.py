"""The UI server. One command, no dependency, no build step, and it runs with no API key.

    python -m src.app

WHY A SERVER AT ALL, FOR A KIT THAT IS OTHERWISE FILES.
Because the fork test says a stranger sees the thing WORK before they spend a cent, and a wall of
JSON is not seeing it work. This is the smallest thing that shows the pipeline doing its job: ask a
question, watch which passages won, read the exact prompt that would go to the model, and -- only
if a key is configured -- see the answer.

THIS FILE HOLDS NO PIPELINE LOGIC AND THAT IS DELIBERATE.
Every answer below comes from a module the eval harness already drives: `index.load`,
`retrieve.retrieve`, `prompt.assemble`, `adapters.complete`. If the UI computed anything itself it
would be a second code path describing the pipeline, and a description is the thing that drifts
away from what actually ran. When the numbers on screen disagree with results/, the bug is in the
pipeline, never in a copy of it kept here.

WHAT NEEDS A KEY AND WHAT DOES NOT.
Retrieval, prompt assembly, the corpus statistics and every recorded result are pure code over
checked-in files: no key, no network, deterministic. Only the final completion needs a credential,
and when there is none the UI says so in words instead of failing at the HTTP layer. The key is
read from the environment or .env by src/config.py, is never logged, and is never sent anywhere
except the provider you configured.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import chunk as ch, config, index as ix, prompt as pr, retrieve as rt   # noqa: E402

UI = os.path.join(HERE, "ui")
RESULTS = os.path.join(HERE, "results")
LABELS = os.path.join(HERE, "data", "labelled.jsonl")

STATE = {}          # index + labels, loaded once at startup rather than per request


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def load_state():
    STATE["index"] = ix.load()
    STATE["labels"] = {}
    if os.path.exists(LABELS):
        for line in open(LABELS, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                STATE["labels"][r["id"]] = r
    return STATE


# --------------------------------------------------------------------------- endpoints

def api_status():
    """What the kit can do RIGHT NOW. `has_key` is a boolean and the key itself never appears."""
    cfg = config.load()
    idx = STATE["index"]
    return {"corpus": {"documents": idx["documents"], "chunks": len(idx["chunks"]),
                       "by_format": idx["by_format"]},
            "retriever": "embedding" if idx.get("vectors") else "keyword",
            "embed_model": idx.get("embed_model"),
            "provider": cfg["provider"] or None,
            "model": cfg["model"] or None,
            "has_key": config.has_key(cfg),
            "top_k": rt.TOP_K}


def api_ask(question, label_id=None):
    """Retrieve, assemble, and answer only if a key is configured.

    `label_id` is optional and only ever ADDS information: when the question came from the
    labelled set we know which document should have won, so the UI can show a retrieval failure
    as a failure instead of as a confident wrong answer. Free-typed questions have no expectation
    to compare against, and the response says so rather than inventing one.
    """
    idx, cfg = STATE["index"], config.load()
    t0 = time.time()
    mode, hits = rt.retrieve(question, idx)
    ms = round((time.time() - t0) * 1000, 2)
    system, user, parts = pr.assemble(question, hits)

    out = {"question": question, "retriever": mode, "retrieval_ms": ms,
           "hits": [{"id": h["id"], "doc": h["doc"], "format": h["format"],
                     "score": h["score"], "text": h["text"]} for h in hits],
           "prompt": {"system": system, "user": user, "chars": len(user),
                      "parts": [{"name": p["name"], "chars": len(p["text"]),
                                 "doc": p.get("doc"), "chunk": p.get("chunk")} for p in parts]},
           "expected": None, "answer": None, "note": None}

    label = STATE["labels"].get(label_id or "")
    if label:
        joined = _norm(" ".join(h["text"] for h in hits))
        present = all(_norm(f) in joined for f in label["answer_contains"])
        out["expected"] = {"id": label["id"], "doc": label["doc"],
                           "fragments": label["answer_contains"],
                           "doc_retrieved": label["doc"] in [h["doc"] for h in hits],
                           "answer_in_prompt": present,
                           # Named from the taxonomy the harness uses, not invented here.
                           "cause": None if present else "bad_ranking"}

    if not config.has_key(cfg):
        out["note"] = ("no API_KEY configured -- the model half is skipped. Everything above ran "
                       "offline, for free, from the checked-in index.")
        return out
    try:
        from src.adapters import complete
        t1 = time.time()
        got = complete(cfg, system, user)
        out["answer"] = {"text": got["text"], "model": cfg["model"], "provider": cfg["provider"],
                         "input_tokens": got["input_tokens"], "output_tokens": got["output_tokens"],
                         "latency_ms": round((time.time() - t1) * 1000, 2)}
    except Exception as e:
        # The provider's own message, not a status code. "Your key is for a different model"
        # rendered as "400" is the error that costs an afternoon.
        out["note"] = "the model call failed: %s" % e
    return out


def api_results():
    """Every recorded run in results/, newest filename last. These ship in the repo so a fresh
    clone shows real measured output before anyone configures anything."""
    out = []
    for name in sorted(os.listdir(RESULTS)) if os.path.isdir(RESULTS) else []:
        if name.endswith(".json"):
            out.append(json.load(open(os.path.join(RESULTS, name), encoding="utf-8")))
    return {"runs": out}


def api_corpus():
    """Seams 2 and 3 -- extraction and chunking -- which a query never touches.

    This is the tab that answers "can I point this at my own documents", and every number in it is
    already recorded in chunks.json by the index build. Nothing is recomputed here.
    """
    idx = STATE["index"]
    docs = {}
    for c in idx["chunks"]:
        d = docs.setdefault(c["doc"], {"doc": c["doc"], "format": c["format"], "chunks": 0,
                                       "chars": 0})
        d["chunks"] += 1
        d["chars"] += len(c["text"])
    lens = sorted(len(c["text"]) for c in idx["chunks"])
    n = len(lens)
    return {"documents": sorted(docs.values(), key=lambda d: d["doc"]),
            "by_format": idx["by_format"],
            # The ceiling is READ FROM THE CHUNKER, never retyped. A cap the UI states from its
            # own copy is a cap that can disagree with the one actually enforced.
            "chunk_chars": {"count": n, "p50": lens[n // 2], "p90": lens[int(n * 0.9)],
                            "max": lens[-1], "ceiling": ch.MAX},
            "boilerplate": idx.get("boilerplate") or {},
            "extraction_failures": idx.get("extraction_failures") or []}


def api_doc(doc_id):
    """One document's chunks, in order, with their boundaries -- the clearest explanation of
    seam 3 available, because you can see exactly where the splitter cut."""
    chunks = [c for c in STATE["index"]["chunks"] if c["doc"] == doc_id]
    chunks.sort(key=lambda c: c.get("ordinal", 0))
    return {"doc": doc_id, "chunks": [{"id": c["id"], "chars": len(c["text"]),
                                       "text": c["text"]} for c in chunks]}


# --------------------------------------------------------------------------- server

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass                                    # the console is for the kit's output, not a log

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        path = u.path
        try:
            if path == "/api/status":
                return self._json(api_status())
            if path == "/api/results":
                return self._json(api_results())
            if path == "/api/corpus":
                return self._json(api_corpus())
            if path == "/api/doc":
                return self._json(api_doc((q.get("id") or [""])[0]))
            if path == "/api/ask":
                question = (q.get("q") or [""])[0].strip()
                if not question:
                    return self._json({"error": "ask with ?q=your+question"}, 400)
                return self._json(api_ask(question, (q.get("id") or [None])[0]))
            if path == "/api/labels":
                return self._json({"labels": list(STATE["labels"].values())})

            name = "index.html" if path == "/" else path.lstrip("/")
            full = os.path.normpath(os.path.join(UI, name))
            if not full.startswith(UI) or not os.path.isfile(full):
                return self._send(404, "not found", "text/plain; charset=utf-8")
            ext = os.path.splitext(full)[1]
            return self._send(200, open(full, "rb").read(),
                              MIME.get(ext, "application/octet-stream"))
        except Exception as e:
            return self._json({"error": str(e)}, 500)


def main():
    ap = argparse.ArgumentParser(description="docs-qa -- ask questions over your own documents")
    ap.add_argument("--port", type=int, default=8765,
                    help="default 8765, not 8000: 8000 is the first port every other local "
                         "server takes, and a collision at startup reads as a broken kit")
    ap.add_argument("--open", action="store_true",
                    help="open a browser. Off by default -- hijacking the screen is not the same "
                         "as being easy to run, and it misbehaves over SSH and in containers")
    a = ap.parse_args()

    load_state()
    st = api_status()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError as e:
        raise SystemExit("could not listen on port %d (%s).\nAnother process is probably using "
                         "it -- try:  python -m src.app --port %d" % (a.port, e, a.port + 1))

    print("docs-qa  %d documents, %d chunks, retriever=%s"
          % (st["corpus"]["documents"], st["corpus"]["chunks"], st["retriever"]))
    if st["has_key"]:
        print("         model %s via %s -- live answers are ON" % (st["model"], st["provider"]))
    else:
        print("         no API_KEY -- retrieval, prompts and recorded results all work offline.")
        print("         Copy .env.example to .env and add a key to get live answers.")
    print("\n         http://127.0.0.1:%d\n" % a.port)
    if a.open:
        import webbrowser
        webbrowser.open("http://127.0.0.1:%d" % a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
