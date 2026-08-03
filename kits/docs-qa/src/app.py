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
import urllib.error
import urllib.parse
import urllib.request
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


def api_connect(body):
    """POST /api/connect — point the kit at a model, from the kit's own UI.

    IT PROBES BEFORE IT SAVES, AND THE PROBE IS FREE. A bare "saved" tells you nothing: the whole
    failure this replaces is a .env that looks filled in and is not. So it asks the endpoint for its
    model list first -- GET /models, which every OpenAI-compatible provider serves and none of them
    charge for -- and reports what came back. That single call is what unblocked a run here after
    an afternoon of guessing: the list named the two models that actually exist, so the base URL and
    the key were both confirmed without spending anything.

    WHAT REFUSES TO SAVE, AND WHY EACH ONE. A rejected key (401/403) and an unreachable host are
    saved-nowhere, because both mean the value in front of you is wrong and writing it down only
    buries the error. A provider that has no /models route (404) IS saved, marked unverified --
    refusing there would lock out a working provider over a route that is not required to exist.

    THE KEY IS NEVER RETURNED, NEVER LOGGED AND NEVER PUT IN A URL. It goes into one header and
    into a 0600 file. api_status() has always answered with a boolean for the same reason.
    """
    base = str(body.get("base_url") or "").strip().rstrip("/")
    key = str(body.get("api_key") or "").strip()
    model = str(body.get("model") or "").strip()
    provider = str(body.get("provider") or "openai-compatible").strip()
    if not base or not key:
        return {"ok": False, "error": "a base URL and a key are both needed"}
    if not base.startswith(("http://", "https://")):
        return {"ok": False, "error": "the base URL must start with http:// or https://"}

    listed, verified, note = [], False, ""
    req = urllib.request.Request(base + "/models",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        listed = sorted(str(m.get("id")) for m in (data.get("data") or []) if m.get("id"))
        verified = True
        if model and listed and model not in listed:
            # NOT a refusal. Providers alias and version model names, and a list that does not
            # mention yours is a reason to look twice rather than a reason to overrule someone
            # about their own account.
            note = ("saved, but %r is not in the %d models this endpoint lists — check the "
                    "spelling against the list below." % (model, len(listed)))
        elif listed:
            note = "endpoint and key confirmed: %d models listed." % len(listed)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False,
                    "error": "the endpoint rejected that key (HTTP %d). Nothing was saved."
                             % e.code}
        note = ("saved unverified: this endpoint has no /models route (HTTP %d), which is allowed. "
                "The first question you ask will be the real test." % e.code)
    except Exception as e:
        return {"ok": False,
                "error": "could not reach %s (%s). Nothing was saved." % (base, e)}

    path = config.save({"PROVIDER": provider, "BASE_URL": base, "API_KEY": key, "MODEL": model})
    return {"ok": True, "verified": verified, "models": listed[:60], "note": note,
            "wrote": os.path.basename(path), "status": api_status()}


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

    def do_POST(self):
        """The only write this server accepts. Three things keep it safe, and the loopback bind is
        NOT one of them — any page in the browser can reach 127.0.0.1.

        1. POST ONLY. No link, redirect, <img> or prefetch can fire it, so it cannot be triggered
           by a page merely being open.
        2. application/json REQUIRED. A cross-origin form or fetch cannot send that content type
           without a CORS preflight, and this server answers no preflight and sets no CORS header —
           so a page on another origin cannot reach it at all. Relaxing the content-type check is
           what would undo that, which is why it is checked here rather than left to the parser.
        3. NOTHING IS ECHOED. The reply carries a boolean and a model list; the value written is
           never read back out of this process.
        """
        u = urllib.parse.urlparse(self.path)
        if u.path != "/api/connect":
            return self._json({"error": "not found"}, 404)
        ctype = (self.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return self._json({"error": "send application/json"}, 415)
        try:
            length = int(self.headers.get("content-length") or 0)
            if length <= 0 or length > 8192:
                return self._json({"error": "expected a small JSON body"}, 400)
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                return self._json({"error": "expected a JSON object"}, 400)
            # NO RESTART IS NEEDED AND NO CACHE IS INVALIDATED HERE: config.load() reads .env on
            # every call, which is why api_connect can return a fresh api_status() in the same
            # reply. If that ever becomes a cached read, this is the place that has to change with
            # it — a save the next question does not see reads exactly like a save that failed.
            out = api_connect(body)
            return self._json(out, 200 if out.get("ok") else 400)
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
