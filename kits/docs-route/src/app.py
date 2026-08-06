"""The minimal local UI. Standard library only — python -m src.app, then open the printed URL.

WHAT IT IS FOR. One document, one routing decision, on your machine, with your key. It is the proof
that this runs on a laptop and it is the only thing in the kit that starts a process. It is NOT the
published board: the boards live in the Foundry site, rendered from committed run records.

IT RENDERS WITH NO KEY. /api/queues and /api/doc need nothing, and /api/baseline runs the keyword
router for free — so the page is fully explorable, including a real routing decision, before anyone
spends anything. Only /api/route calls a provider.

⚑ AND IT SHOWS THE GUARDRAIL WORKING, WHICH IS THE POINT OF THIS PARTICULAR UI. The panel does not
just print a queue: it prints the confidence, the floor, and whether the floor overrode the model.
A router demo that showed only the answer would hide the one behaviour a buyer needs to see —
what happens when the model is unsure. `escalated` is rendered as its own state, in its own colour,
never as a failure.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, route as R, taxonomy as TX     # noqa: E402
from evals import baseline as B                        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port: docs-qa 8765, docs-extract 8766, docs-summarise 8767. Starting the fourth kit
# while the others are up must not die with a traceback ending in "Address already in use".
PORT = int(os.environ.get("PORT", "8768"))


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
        if u.path == "/api/queues":
            cfg = config.load()
            return self._send(200, {
                "queues": [{"key": k, "label": TX.label_of(k), "meaning": TX.meaning(k)}
                           for k in TX.ORDER],
                "abstain": TX.ABSTAIN,
                "floor": R.CONFIDENCE_FLOOR,
                "documents": R.documents(),
                # The page states what it is pointed at and whether it can spend. A demo that
                # looks identical with and without a key is a demo that cannot be trusted about
                # which of its numbers came from a model.
                "model": cfg.get("model"),
                "has_key": config.has_key(cfg),
            })
        if u.path == "/api/doc":
            did = (parse_qs(u.query).get("id") or [""])[0]
            if did not in R.documents():
                return self._send(404, {"error": "no such document"})
            return self._send(200, {"doc_id": did, "text": R.load_doc(did)})
        if u.path == "/api/baseline":
            did = (parse_qs(u.query).get("id") or [""])[0]
            if did not in R.documents():
                return self._send(404, {"error": "no such document"})
            pred = B.keyword_predict(R.load_doc(did))
            return self._send(200, {"doc_id": did, "queue": pred["queue"],
                                    "label": TX.label_of(pred["queue"]) if pred["queue"] else None,
                                    "state": pred["state"], "rule": pred.get("rule")})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/route":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        did = body.get("id")
        if did not in R.documents():
            return self._send(404, {"error": "no such document"})
        cfg = config.load()
        if not config.has_key(cfg):
            # 200, not an error. A missing key is a normal state for someone reading the page,
            # and an error card here would look like the kit is broken.
            return self._send(200, {"doc_id": did, "no_key": True,
                                    "message": "No API_KEY configured, so no model was called. "
                                               "The keyword baseline above needs no key and is "
                                               "the thing a model has to beat."})
        try:
            rec = R.decide(cfg, R.load_doc(did), floor=body.get("floor", R.CONFIDENCE_FLOOR))
        except Exception as exc:
            return self._send(200, {"doc_id": did, "error": "%s: %s" % (type(exc).__name__, exc)})
        rec["doc_id"] = did
        rec["outcome"] = R.outcome(rec)
        rec["label"] = TX.label_of(rec["routed_to"]) if rec["routed_to"] else None
        return self._send(200, rec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()
    cfg = config.load()
    print("docs-route — %d document(s), %d queue(s), floor %.2f"
          % (len(R.documents()), len(TX.ORDER), R.CONFIDENCE_FLOOR))
    print("model: %s   key configured: %s"
          % (cfg.get("model") or "(none set)", "yes" if config.has_key(cfg) else "no"))
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise SystemExit("port %d is already in use — another kit's app is probably running. "
                             "Try: python -m src.app --port %d" % (a.port, a.port + 10))
        raise
    print("open http://127.0.0.1:%d" % a.port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
