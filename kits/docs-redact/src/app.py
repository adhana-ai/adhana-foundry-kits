"""The minimal local UI. Standard library only — python -m src.app, then open the printed URL.

WHAT IT IS FOR. One document, one detection call, on your machine, with your key. It is the proof
that this runs on a laptop and it is the only thing in the kit that starts a process. It is NOT the
published dashboard: the boards that grade the run live in the Foundry site, from committed run
records, and pushing them in here would drag a measurement layer into a repo that ships a kit.

IT RENDERS WITH NO KEY. /api/categories and /api/doc need nothing; only /api/redact calls a
provider, and with no API_KEY it returns a 200 saying so rather than an error, so the page is
explorable before anyone spends anything.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, detect as D, redact as R          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port: docs-qa 8765, docs-extract 8766, docs-summarise 8767, docs-route 8768,
# docs-redline 8769. Starting this kit while an earlier one is still up must not die with a
# nine-line traceback ending in "Address already in use" — see the handling below.
PORT = int(os.environ.get("PORT", "8770"))


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass                                    # the console is for the kit's output, not access logs

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(UI, "index.html"), "rb").read(),
                              "text/html; charset=utf-8")
        if u.path in ("/app.js", "/app.css"):
            ct = "text/javascript" if u.path.endswith(".js") else "text/css"
            return self._send(200, open(os.path.join(UI, u.path[1:]), "rb").read(),
                              ct + "; charset=utf-8")
        if u.path == "/api/categories":
            return self._send(200, {"categories": D.load_categories(),
                                    "documents": D.documents(),
                                    "has_key": config.has_key()})
        if u.path == "/api/doc":
            doc_id = (parse_qs(u.query).get("id") or [""])[0]
            if doc_id not in D.documents():
                return self._send(404, {"error": "no such document"})
            return self._send(200, {"id": doc_id, "text": D.load_doc(doc_id)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/redact":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "body must be JSON"})
        # ⚑ PASTE-YOUR-OWN, NOT ONLY THE SHIPPED CORPUS. `text` in the body wins over `id` when
        # both are present, so the UI's "paste a document" box (the concept the wireframe was built
        # to prove out) needs no server-side change to work — this endpoint already accepts
        # arbitrary text, it just also knows how to look one up by id for convenience.
        doc_id = req.get("id")
        text = req.get("text")
        if text is None:
            if doc_id not in D.documents():
                return self._send(404, {"error": "no such document, and no text was supplied"})
            text = D.load_doc(doc_id)
        cfg = config.load()
        if not config.has_key(cfg):
            # 200, not an error: "no key" is a configuration state the page should render calmly.
            return self._send(200, {"id": doc_id, "spans": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = D.detect(cfg, text, D.load_categories())
        except Exception as exc:
            # ⚠︎ THE PROVIDER'S MESSAGE IS RETURNED, THE CONFIGURATION IS NOT. A base URL or a key
            # can hold anything, so no secret's VALUE reaches the page, not even inside an error.
            msg = str(exc)
            for k in ("api_key", "base_url"):
                v = cfg.get(k)
                if v:
                    msg = msg.replace(v, "[%s]" % k.upper())
            return self._send(200, {"id": doc_id, "spans": None, "note": msg[:500]})
        return self._send(200, {
            "id": doc_id,
            "spans": r["spans"],
            "unlocated": r["unlocated"],
            "redacted": R.mask(text, r["spans"]),
            "highlighted": R.highlight(text, r["spans"]),
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
        })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT,
                    help="default %d. The PORT environment variable works too." % PORT)
    a = ap.parse_args()

    cfg = config.load()
    # ⚠︎ BIND FIRST, ANNOUNCE SECOND — the order docs-extract's app.py settled on after printing a
    # URL that was never going to answer. Anything that prints a promise before keeping it can
    # print a false one.
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            "Port %d is already in use.\n"
            "\n"
            "Most likely that is another kit's UI. Both can run at once; they just need different\n"
            "ports.\n"
            "\n"
            "  python -m src.app --port %d          # or: PORT=%d python -m src.app\n"
            "\n"
            "To see what is holding it:  lsof -nP -iTCP:%d -sTCP:LISTEN"
            % (a.port, a.port + 1, a.port + 1, a.port))

    print("docs-redact UI  ->  http://127.0.0.1:%d" % a.port)
    print("  documents: %d   categories: %d   API_KEY: %s"
          % (len(D.documents()), len(D.load_categories()),
             "set" if config.has_key(cfg) else "not set (the page still renders)"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
