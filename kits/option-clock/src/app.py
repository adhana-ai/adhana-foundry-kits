"""The minimal local UI. Standard library only -- python -m src.app, then open the printed URL.

ONE REGISTER SNAPSHOT, ONE EXTRACTION, on your machine, with your key. It is the proof that this
runs on a laptop; it is NOT the published dashboard, which lives on the Foundry site from committed
run records.

⚠︎ AND IT IS NOT A MONITOR. There is no schedule here, no poller, no queue and no state between
clicks. You pick one snapshot, it reads it once, and it proposes. Nothing runs when you are not
looking at it.

IT RENDERS WITH NO KEY. /api/fields, /api/doc and /api/rulebook need nothing; only /api/extract
calls a provider, and with no API_KEY it returns 200 saying so rather than an error.

⚑ THE RULEBOOK IS SERVED TO THE PAGE, NOT DESCRIBED TO IT. /api/rulebook returns data/rulebook.json
verbatim, so the rules the count was made under are one click away from the count itself -- and the
"illustrative, not an authority" line the reader needs is on the same screen as the answer rather
than in a file they will never open.
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
from src import rulebook as RB                 # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# ⚑ EVERY KIT PICKS ITS OWN PORT SO TWO CAN RUN AT ONCE. 8843 was free when this kit was written;
# `lsof -nP -iTCP:8843 -sTCP:LISTEN` says whether it still is, and --port moves it either way.
PORT = int(os.environ.get("PORT", "8843"))


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
                                    "window_days": RB.WINDOW_DAYS,
                                    "has_key": config.has_key()})
        if u.path == "/api/rulebook":
            return self._send(200, RB.load())
        if u.path == "/api/doc":
            sid = (parse_qs(u.query).get("id") or [""])[0]
            if sid not in EX.documents():
                return self._send(404, {"error": "no such register"})
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
            return self._send(404, {"error": "no such register"})
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
                                "escalate_now": r["escalate_now"],
                                "counted_status": r["counted_status"],
                                "counted_expiry_date": r["counted_expiry_date"],
                                "counted_clock_start_date": r["counted_clock_start_date"],
                                "counted_days_to_expiry": r["counted_days_to_expiry"],
                                "reason": r["counted_reason"],
                                "undetermined_because": r["undetermined_because"],
                                "window_days": r["window_days"],
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

    print("option-clock UI  ->  http://127.0.0.1:%d" % a.port)
    print("  registers: %d   fields: %d   window: %d days   API_KEY: %s"
          % (len(EX.documents()), len(EX.load_fields()), RB.WINDOW_DAYS,
             "set" if config.has_key(cfg) else "not set (the page still renders)"))
    print("  the shipped rulebook is ILLUSTRATIVE and is not an authority; this kit proposes a "
          "worklist, watches nothing, and never exercises, renews or lapses anything")
    srv.serve_forever()


if __name__ == "__main__":
    main()
