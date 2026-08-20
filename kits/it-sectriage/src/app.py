"""The minimal local UI. Standard library only -- python -m src.app, then open the printed URL.

WHAT IT IS FOR. One case window, one triage call, on your machine, with your key. It is the proof
that this runs on a laptop and it is the only thing in the kit that starts a process. It is NOT the
published dashboard: the boards that grade the run live in the Foundry site, from committed run
records.

IT RENDERS WITH NO KEY. /api/state and /api/window need nothing; only /api/triage calls a
provider, and with no API_KEY it returns a 200 saying so rather than an error, so the page is
explorable before anyone spends anything.

⚠︎ THE SHARED `.env` MEANS A BRAND-NEW KIT ALREADY HAS A LIVE KEY. Every kit under this repo root
inherits the root `.env`, so "there is no key configured yet" is a false assumption on a fresh kit
-- touching a model endpoint spends money immediately. /api/state reports `has_key` so the UI can
show the state, and nothing here calls a model as a side effect of loading a page.

⚑ THIS SERVER NEVER EXECUTES A CONTAINMENT ACTION. /api/triage returns dispositions, case
groupings and a drafted recommendation and nothing else -- there is no endpoint here that locks an
account, blocks mail flow or isolates an endpoint. See src/triage.py's module docstring for the
same boundary stated in the AI layer.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, triage as T                          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port; see sibling kits' src/app.py headers for the rest of the range. 8789 was the
# highest taken as of this kit's build; picking clear of it leaves room for same-night siblings.
PORT = int(os.environ.get("PORT", "8792"))


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
        if u.path == "/api/state":
            wins = T.windows()
            gold = T.load_gold()
            fn = sum(1 for g in gold.values() if g["trap"] == "false_negative")
            fc = sum(1 for g in gold.values() if g["trap"] == "false_correlation")
            return self._send(200, {
                "windows": [w["id"] for w in wins], "has_key": config.has_key(),
                "gate": {"windows": len(wins), "alerts": sum(len(w["alerts"]) for w in wins),
                        "false_negative_trap_windows": fn, "false_correlation_trap_windows": fc}})
        if u.path == "/api/window":
            wid = (parse_qs(u.query).get("id") or [""])[0]
            match = next((w for w in T.windows() if w["id"] == wid), None)
            if not match:
                return self._send(404, {"error": "no such window"})
            gold = T.load_gold().get(wid, {})
            return self._send(200, {"window": match,
                                    "trap": gold.get("trap"),
                                    "gold_case_groups": gold.get("case_groups"),
                                    "gold_alert_dispositions": gold.get("alert_dispositions")})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/triage":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "body must be JSON"})
        wid = req.get("id")
        match = next((w for w in T.windows() if w["id"] == wid), None)
        if not match:
            return self._send(404, {"error": "no such window"})
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"id": wid, "alert_dispositions": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = T.check(cfg, match)
        except Exception as exc:
            msg = str(exc)
            for k in ("api_key", "base_url"):
                v = cfg.get(k)
                if v:
                    msg = msg.replace(v, "[%s]" % k.upper())
            return self._send(200, {"id": wid, "alert_dispositions": None, "note": msg[:500]})
        return self._send(200, {
            "id": wid,
            "alert_dispositions": r["alert_dispositions"],
            "case_groups": r["case_groups"],
            "recommendations": r["recommendations"],
            "parsed": r["parsed"],
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

    wins = T.windows()
    print("it-sectriage UI  ->  http://127.0.0.1:%d" % a.port)
    print("  windows: %d   alerts: %d   API_KEY: %s"
          % (len(wins), sum(len(w["alerts"]) for w in wins),
             "set" if config.has_key(cfg) else "not set (the page still renders)"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
