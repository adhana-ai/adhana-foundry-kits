"""The minimal local UI. Standard library only -- python -m src.app, then open the printed URL.

WHAT IT IS FOR. One review batch, one drafting call, on your machine, with your key. It is the
proof that this runs on a laptop. It is NOT the published dashboard: the boards that grade the full
run live on the Foundry site, from committed run records.

IT RENDERS WITH NO KEY. /api/state and /api/batch need nothing -- they show the code-computed
material exceptions and the merchant notes log. Only /api/draft calls a provider, and with no
API_KEY it returns a 200 saying so rather than an error, so the page is explorable before anyone
spends anything.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import brief as B, config, segment as SEG, pack as PACK          # noqa: E402
from src import adapters                                                    # noqa: E402
from evals import scoring as SC                                              # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port; see sibling kits' src/app.py headers for the rest of the range.
PORT = int(os.environ.get("PORT", "8786"))

_CACHE = {}


def _corpus():
    if "batches" not in _CACHE:
        _CACHE["batches"] = B.batches()
        _CACHE["notes"] = B.notes_by_id()
        _CACHE["gold"] = B.gold_by_id()
    return _CACHE["batches"], _CACHE["notes"], _CACHE["gold"]


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(UI, "index.html"), "rb").read(),
                              "text/html; charset=utf-8")
        if u.path in ("/app.js", "/app.css"):
            ct = "text/javascript" if u.path.endswith(".js") else "text/css"
            return self._send(200, open(os.path.join(UI, u.path[1:]), "rb").read(),
                              ct + "; charset=utf-8")
        batches, notes, gold = _corpus()
        if u.path == "/api/state":
            return self._send(200, {"batches": [b["batch_id"] for b in batches],
                                    "has_key": config.has_key()})
        if u.path == "/api/batch":
            bid = (parse_qs(u.query).get("id") or [""])[0]
            b = next((x for x in batches if x["batch_id"] == bid), None)
            if not b:
                return self._send(404, {"error": "no such batch"})
            exceptions = SEG.material_exceptions(b)
            packed, meta = PACK.pack(b, notes.get(bid, []), exceptions)
            return self._send(200, {"batch": b, "packed": packed, "pack_meta": meta,
                                    "all_items": SEG.flag_batch(b)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/draft":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "body must be JSON"})
        bid = req.get("batch_id")
        batches, notes, gold = _corpus()
        b = next((x for x in batches if x["batch_id"] == bid), None)
        if not b:
            return self._send(404, {"error": "no such batch"})
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"batch_id": bid, "answer": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = B.draft(cfg, b, notes.get(bid, []), thinking=adapters.THINKING_OFF)
        except Exception as exc:
            msg_txt = str(exc)
            for k in ("api_key", "base_url"):
                val = cfg.get(k)
                if val:
                    msg_txt = msg_txt.replace(val, "[%s]" % k.upper())
            return self._send(200, {"batch_id": bid, "answer": None, "note": msg_txt[:500]})

        # ⚑ THE CITATION-FIDELITY CHECK RUNS HERE, ON EVERY LIVE DRAFT, NOT ONLY IN evals/run.py.
        # A reader of the UI sees a fabrication flagged the same second the model returns one --
        # the guardrail is not something that only shows up after the fact in a committed eval
        # result. Uses the identical predicate evals/scoring.py grades the real run with, so the
        # UI and the published board can never quietly disagree about what counts as fabricated.
        notes_text = "\n".join(notes.get(bid, []))
        item_by_id = {f["item_id"]: f for f in SEG.material_exceptions(b)}
        for entry in r["answer"]["items"]:
            f = item_by_id.get(entry["item_id"])
            item_label = f["item_label"] if f else ""
            if entry.get("cause") and entry["cause"] != "unknown":
                c1_ok = (SC.citation_is_real(entry.get("citation_1"), notes_text)
                        and SC.citation_is_relevant(entry.get("citation_1"), item_label))
                c2_ok = (SC.citation_is_real(entry.get("citation_2"), notes_text)
                        and SC.citation_is_relevant(entry.get("citation_2"), item_label))
                entry["citation_ok"] = bool(c1_ok and c2_ok)
            else:
                entry["citation_ok"] = None          # not applicable -- cause is 'unknown'

        return self._send(200, {
            "batch_id": bid, "answer": r["answer"], "items_material": r["items_material"],
            "items_answered": r["items_answered"],
            "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
        })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT,
                    help="default %d. The PORT environment variable works too." % PORT)
    a = ap.parse_args()

    cfg = config.load()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            "Port %d is already in use.\n\nMost likely that is another kit's UI. Both can run at "
            "once; they just need different ports.\n\n"
            "  python -m src.app --port %d          # or: PORT=%d python -m src.app\n\n"
            "To see what is holding it:  lsof -nP -iTCP:%d -sTCP:LISTEN"
            % (a.port, a.port + 1, a.port + 1, a.port))

    batches, _, _ = _corpus()
    print("exception-brief UI  ->  http://127.0.0.1:%d" % a.port)
    print("  batches: %d   API_KEY: %s"
          % (len(batches), "set" if config.has_key(cfg) else "not set (the page still renders)"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
