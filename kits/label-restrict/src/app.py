"""The minimal local UI. Standard library only -- python -m src.app, then open the printed URL.

ONE LABEL EXTRACT AND ONE PROPOSED APPLICATION, ONE EXTRACTION, on your machine, with your key. It
is the proof that this runs on a laptop; it is NOT the published dashboard, which lives on the
Foundry site from committed run records.

IT RENDERS WITH NO KEY. /api/fields, /api/doc and /api/checks need nothing; only /api/extract calls
a provider, and with no API_KEY it returns 200 saying so rather than an error.

⚑ THE CHECK SET IS SERVED TO THE PAGE, NOT DESCRIBED TO IT. /api/checks returns data/checks.json
verbatim, so the eight restrictions the verdict was decided by are one click away from the verdict
itself -- and the "illustrative, not an authority" line the reader needs is on the same screen as
the answer rather than in a file they will never open.

⚑ AND THE WALK IS SERVED WITH IT. /api/extract returns the state of every check -- pass, breach,
not applicable, not stated -- not just the one that fired. A verdict with one named restriction
under it is a claim; the same verdict with all eight states beside it is something a reader can
audit in ten seconds.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, extract as EX          # noqa: E402
from src import checks as CK                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# ⚑ EVERY KIT PICKS ITS OWN PORT SO TWO CAN RUN AT ONCE. 8802 was free when this kit was written;
# `lsof -nP -iTCP:8802 -sTCP:LISTEN` says whether it still is, and --port moves it either way.
PORT = int(os.environ.get("PORT", "8802"))


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
        if u.path == "/api/fields":
            return self._send(200, {"fields": EX.load_fields(),
                                    "documents": EX.documents(),
                                    "has_key": config.has_key()})
        if u.path == "/api/checks":
            return self._send(200, CK.load())
        if u.path == "/api/doc":
            sid = (parse_qs(u.query).get("id") or [""])[0]
            if sid not in EX.documents():
                return self._send(404, {"error": "no such case"})
            return self._send(200, {"id": sid, "text": EX.load_doc(sid)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/extract":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "body must be JSON"})
        sid = req.get("id")
        if sid not in EX.documents():
            return self._send(404, {"error": "no such case"})
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"id": sid, "fields": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = EX.extract(cfg, EX.load_doc(sid), EX.load_fields())
        except Exception as exc:
            msg = str(exc)
            for k in ("api_key", "base_url"):
                v = cfg.get(k)
                if v:
                    msg = msg.replace(v, "[%s]" % k.upper())
            return self._send(200, {"id": sid, "fields": None, "note": msg[:500]})
        return self._send(200, {"id": sid, "fields": r["fields"],
                                "needs_hold": r["needs_hold"],
                                "reason": r["recomputed_reason"],
                                "recomputed_verdict": r["recomputed_verdict"],
                                "recomputed_restriction": r["recomputed_restriction"],
                                "checks": r["recomputed_checks"],
                                "sections_used": r["sections_used"],
                                "input_tokens": r["input_tokens"],
                                "output_tokens": r["output_tokens"]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()

    cfg = config.load()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            "Port %d is already in use.\n\nMost likely another kit's UI is running.\n\n"
            "  python -m src.app --port %d          # or: PORT=%d python -m src.app\n\n"
            "To see what is holding it:  lsof -nP -iTCP:%d -sTCP:LISTEN"
            % (a.port, a.port + 1, a.port + 1, a.port))

    print("label-restrict UI  ->  http://127.0.0.1:%d" % a.port)
    print("  cases: %d   fields: %d   API_KEY: %s"
          % (len(EX.documents()), len(EX.load_fields()),
             "set" if config.has_key(cfg) else "not set (the page still renders)"))
    print("  the shipped check set is ILLUSTRATIVE and is not an authority; this kit proposes a "
          "reading of a label and never authorises an application")
    srv.serve_forever()


if __name__ == "__main__":
    main()
