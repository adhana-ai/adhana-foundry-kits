"""The minimal local UI. Standard library only -- python -m src.app, then open the printed URL.

WHAT IT IS FOR. One parameter, one review call, on your machine, with your key. It is the proof
that this runs on a laptop. It is NOT the published dashboard: the boards that grade the full run
live on the Foundry site, from committed run records.

IT RENDERS WITH NO KEY. /api/state, /api/parameter and /api/floor need nothing; only /api/check
calls a provider, and with no API_KEY it returns a 200 saying so rather than an error, so the page
is explorable before anyone spends anything.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import aggregate as A, config, formulas as F, triage as T          # noqa: E402
from src import adapters                                                     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port; see sibling kits' src/app.py headers for the rest of the range.
PORT = int(os.environ.get("PORT", "8782"))

_CACHE = {}


def _corpus():
    if "params" not in _CACHE:
        _CACHE["params"] = T.load_parameters()
        _CACHE["windows"] = T.windows()
        _CACHE["gold"] = T.labels_by_id()
    return _CACHE["params"], _CACHE["windows"], _CACHE["gold"]


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
        params, wins, gold = _corpus()
        if u.path == "/api/state":
            return self._send(200, {"parameters": [p["parameter_id"] for p in params],
                                    "has_key": config.has_key()})
        if u.path == "/api/parameter":
            pid = (parse_qs(u.query).get("id") or [""])[0]
            p = next((x for x in params if x["parameter_id"] == pid), None)
            if not p:
                return self._send(404, {"error": "no such parameter"})
            w = wins[pid]
            fx = A.facts(w)
            return self._send(200, {"parameter": p, "window": w, "facts": fx,
                                    "gold": gold.get(pid)})
        if u.path == "/api/floor":
            pid = (parse_qs(u.query).get("id") or [""])[0]
            p = next((x for x in params if x["parameter_id"] == pid), None)
            if not p:
                return self._send(404, {"error": "no such parameter"})
            fx = A.facts(wins[pid])
            verdict, reasons = F.decide_floor(p["category"], p["configured_value"], fx["stats"])
            proposed = F.corrected_value(p["category"], fx["stats"])
            return self._send(200, {"verdict": verdict, "reasons": reasons,
                                    "proposed_value": proposed})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/check":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "body must be JSON"})
        pid = req.get("parameter_id")
        params, wins, gold = _corpus()
        p = next((x for x in params if x["parameter_id"] == pid), None)
        if not p:
            return self._send(404, {"error": "no such parameter"})
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"parameter_id": pid, "verdict": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = T.check(cfg, p, wins[pid], thinking=adapters.THINKING_OFF)
        except Exception as exc:
            msg_txt = str(exc)
            for k in ("api_key", "base_url"):
                val = cfg.get(k)
                if val:
                    msg_txt = msg_txt.replace(val, "[%s]" % k.upper())
            return self._send(200, {"parameter_id": pid, "verdict": None, "note": msg_txt[:500]})
        return self._send(200, {
            "parameter_id": pid, "verdict": r["verdict"], "reason": r["reason"],
            "proposed_value": r["proposed_value"], "deviation": r["deviation"],
            "floor_verdict": r["floor_verdict"], "floor_reasons": r["floor_reasons"],
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

    params, _, _ = _corpus()
    print("param-drift UI  ->  http://127.0.0.1:%d" % a.port)
    print("  parameters: %d   API_KEY: %s"
          % (len(params), "set" if config.has_key(cfg) else "not set (the page still renders)"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
