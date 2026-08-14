"""The minimal local UI. Standard library only — python3 -m src.app, then open the printed URL.

WHAT IT IS FOR. One document, both conditions, side by side, extracted by both methods. That is
this kit's whole argument in one screen: the same page, once clean and once as a scan hands it
back, with the fields that survived and the fields that did not.

⚑ THE SIDE-BY-SIDE IS THE PRODUCT, NOT A PRESENTATION CHOICE. A single-pane extractor would show
you an answer and give you no way to see what the damage cost — which is the exact blindness the
kit exists to remove.

IT RENDERS WITH NO KEY. /api/doc and /api/floor need nothing — the free floor is pure code — so the
page is fully explorable and the rules-vs-scan comparison works before anyone spends a cent. Only
/api/model calls a provider, and with no API_KEY it returns a 200 saying so.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, prompt as P                       # noqa: E402
from evals import baseline as FLOOR                       # noqa: E402
from evals.score import load_gold, norm                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")
# 8772 — the next free one. Every kit in this repo takes its own, because starting a second kit
# while the first is up dies with "Address already in use", which reads as a broken kit.
PORT = int(os.environ.get("PORT", "8772"))


def _doc(cond, doc_id):
    p = os.path.join(HERE, "data", "corpus", cond, doc_id + ".txt")
    return open(p, encoding="utf-8").read()


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
        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(UI, "index.html"), "rb").read(),
                              "text/html; charset=utf-8")
        for name, ctype in (("app.css", "text/css"), ("app.js", "application/javascript")):
            if u.path == "/" + name:
                return self._send(200, open(os.path.join(UI, name), "rb").read(), ctype)

        if u.path == "/api/docs":
            return self._send(200, {"docs": [{"doc_id": r["doc_id"], "kind": r["kind"]}
                                             for r in load_gold(HERE)]})
        if u.path == "/api/doc":
            d = q.get("id", ["d000"])[0]
            gold = {r["doc_id"]: r for r in load_gold(HERE)}.get(d, {})
            return self._send(200, {"doc_id": d, "clean": _doc("clean", d),
                                    "messy": _doc("messy", d), "gold": gold.get("gold", {})})
        if u.path == "/api/floor":
            d = q.get("id", ["d000"])[0]
            return self._send(200, {"clean": FLOOR.extract(_doc("clean", d)),
                                    "messy": FLOOR.extract(_doc("messy", d))})
        if u.path == "/api/model":
            d = q.get("id", ["d000"])[0]
            cfg = config.load()
            if not config.has_key(cfg):
                # A 200 that says so, not an error. The page stays usable and the free floor —
                # which is the honest half of the comparison anyway — still works.
                return self._send(200, {"skipped": "no API_KEY configured; the free floor above "
                                                   "needs none and is fully live."})
            from src import adapters
            fields = json.load(open(os.path.join(HERE, "data", "fields.json"),
                                    encoding="utf-8"))["fields"]
            out = {}
            for cond in ("clean", "messy"):
                r = adapters.complete(cfg, P.SYSTEM, P.build(fields, _doc(cond, d)),
                                      max_tokens=700)
                try:
                    from evals.run import parse
                    out[cond] = parse(r["text"])
                except Exception as e:                    # noqa: BLE001
                    out[cond] = {"_error": str(e)}
            return self._send(200, out)
        return self._send(404, {"error": "no route"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("docs-messy UI  ->  http://127.0.0.1:%d" % PORT)
    print("the free floor needs no key; /api/model spends 2 calls per document")
    srv.serve_forever()
