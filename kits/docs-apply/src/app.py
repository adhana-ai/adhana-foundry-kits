"""The minimal local UI. Standard library only — python3 -m src.app, then open the printed URL.

WHAT IT IS FOR. One change request, the document before and after, and the diff — including the
lines that changed and were not supposed to. That last part is this kit's whole argument, and it is
the reason the UI is a DIFF rather than a document viewer: showing the result alone would hide
exactly the failure the kit exists to measure.

⚑ THE REFUSAL CASES ARE IN THE SAME PICKER AS THE REST, UNLABELLED UNTIL YOU RUN THEM.
A demo that separates "the ones it should refuse" into their own tab tells the reader the answer
before they have looked. Here you pick a document, run a method, and find out.

IT RENDERS WITH NO KEY. /api/doc and /api/floor need nothing — the free floor is pure code — so the
rules-versus-model comparison is half live before anyone spends a cent. Only /api/model calls a
provider, and with no API_KEY it returns a 200 saying so.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, prompt as P                       # noqa: E402
from evals import baseline as FLOOR                       # noqa: E402
from evals.score import load_requests, load_doc, line_diff, norm   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")
# 8773 — the next free one. Every kit in this repo takes its own, because starting a second kit
# while the first is up dies with "Address already in use", which reads as a broken kit.
PORT = int(os.environ.get("PORT", "8773"))


def _result(doc_id, produced):
    before = load_doc(HERE, "corpus", doc_id)
    gold = load_doc(HERE, "gold", doc_id)
    if produced is None:
        return {"declined": True, "produced": None, "intended": line_diff(before, gold),
                "collateral": []}
    return {"declined": False, "produced": produced,
            "intended": line_diff(before, gold),
            # Collateral is measured against GOLD, so the requested change is never counted as
            # damage — only what moved beyond it.
            "collateral": line_diff(gold, produced),
            "exact": norm(produced) == norm(gold)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        did = q.get("id", ["p000"])[0]

        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(UI, "index.html"), "rb").read(),
                              "text/html; charset=utf-8")
        for name, ctype in (("app.css", "text/css"), ("app.js", "application/javascript")):
            if u.path == "/" + name:
                return self._send(200, open(os.path.join(UI, name), "rb").read(), ctype)

        if u.path == "/api/docs":
            return self._send(200, {"docs": [{"doc_id": r["doc_id"], "request": r["request"]}
                                             for r in load_requests(HERE)]})
        if u.path == "/api/doc":
            row = {r["doc_id"]: r for r in load_requests(HERE)}.get(did, {})
            return self._send(200, {"doc_id": did, "before": load_doc(HERE, "corpus", did),
                                    "request": row.get("request", "")})
        if u.path == "/api/floor":
            before = load_doc(HERE, "corpus", did)
            return self._send(200, _result(did, FLOOR.apply_request(before,
                              {r["doc_id"]: r for r in load_requests(HERE)}[did]["request"])))
        if u.path == "/api/model":
            cfg = config.load()
            if not config.has_key(cfg):
                return self._send(200, {"skipped": "no API_KEY configured; the free floor above "
                                                   "needs none and is fully live."})
            from src import adapters
            from evals.run import parse, MAX_TOKENS
            row = {r["doc_id"]: r for r in load_requests(HERE)}[did]
            before = load_doc(HERE, "corpus", did)
            resp = adapters.complete(cfg, P.SYSTEM, P.build(row["request"], before),
                                     max_tokens=MAX_TOKENS, thinking=adapters.THINKING_OFF)
            try:
                doc, _decision = parse(resp["text"])
            except Exception as e:                        # noqa: BLE001
                return self._send(200, {"error": str(e),
                                        "finish_reason": resp.get("finish_reason")})
            return self._send(200, _result(did, doc))
        return self._send(404, {"error": "no route"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("docs-apply UI  ->  http://127.0.0.1:%d" % PORT)
    print("the free floor needs no key; /api/model spends 1 call per request")
    srv.serve_forever()
