"""The minimal local UI. Standard library only — python -m src.app, then open the printed URL.

WHAT IT IS FOR. One document, one extraction, on your machine, with your key. It is the proof that
this runs on a laptop and it is the only thing in the kit that starts a process. It is NOT the
published dashboard: the boards that grade the run live in the Foundry site, from committed run
records, and pushing them in here would drag a measurement layer into a repo that ships a kit.

IT RENDERS WITH NO KEY. /api/fields and /api/doc need nothing; only /api/extract calls a provider,
and with no API_KEY it returns a 200 saying so rather than an error, so the page is explorable
before anyone spends anything.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, extract as EX          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")
PORT = int(os.environ.get("PORT", "8765"))


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
        if u.path == "/api/fields":
            return self._send(200, {"fields": EX.load_fields(),
                                    "documents": EX.documents(),
                                    "has_key": config.has_key()})
        if u.path == "/api/doc":
            nct = (parse_qs(u.query).get("id") or [""])[0]
            if nct not in EX.documents():
                return self._send(404, {"error": "no such document"})
            return self._send(200, {"id": nct, "text": EX.load_doc(nct)})
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
        nct = req.get("id")
        if nct not in EX.documents():
            return self._send(404, {"error": "no such document"})
        cfg = config.load()
        if not config.has_key(cfg):
            # 200, not an error: "no key" is a configuration state the page should render calmly.
            return self._send(200, {"id": nct, "fields": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = EX.extract(cfg, EX.load_doc(nct), EX.load_fields())
        except Exception as exc:
            # ⚠︎ THE PROVIDER'S MESSAGE IS RETURNED, THE CONFIGURATION IS NOT. A base URL or a key
            # can hold anything, so no secret's VALUE reaches the page, not even inside an error.
            msg = str(exc)
            for k in ("api_key", "base_url"):
                v = cfg.get(k)
                if v:
                    msg = msg.replace(v, "[%s]" % k.upper())
            return self._send(200, {"id": nct, "fields": None, "note": msg[:500]})
        return self._send(200, {"id": nct, "fields": r["fields"],
                                "sections_used": r["sections_used"],
                                "input_tokens": r["input_tokens"],
                                "output_tokens": r["output_tokens"]})


def main():
    cfg = config.load()
    print("docs-extract UI  ->  http://127.0.0.1:%d" % PORT)
    print("  documents: %d   fields: %d   API_KEY: %s"
          % (len(EX.documents()), len(EX.load_fields()),
             "set" if config.has_key(cfg) else "not set (the page still renders)"))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
