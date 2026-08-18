"""The minimal local UI. Standard library only — python -m src.app, then open the printed URL.

WHAT IT IS FOR. One new-item setup request, one match-and-draft call, on your machine, with your
key. It is the proof that this runs on a laptop and it is the only thing in the kit that starts a
process. It is NOT the published dashboard: the boards that grade the run live in the Foundry
site, from committed run records.

IT RENDERS WITH NO KEY. /api/state, /api/request and /api/candidates need nothing; only
/api/check calls a provider, and with no API_KEY it returns a 200 saying so rather than an error,
so the page is explorable before anyone spends anything.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import adapters, block, config, match as M, similarity as SIM    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port; see sibling kits' src/app.py headers for the rest of the range.
PORT = int(os.environ.get("PORT", "8785"))


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
            return self._send(200, {"requests": [r["request_id"] for r in M.load_requests()],
                                    "has_key": config.has_key()})
        if u.path == "/api/request":
            rid = (parse_qs(u.query).get("id") or [""])[0]
            req = next((r for r in M.load_requests() if r["request_id"] == rid), None)
            if not req:
                return self._send(404, {"error": "no such request"})
            return self._send(200, req)
        if u.path == "/api/candidates":
            rid = (parse_qs(u.query).get("id") or [""])[0]
            req = next((r for r in M.load_requests() if r["request_id"] == rid), None)
            if not req:
                return self._send(404, {"error": "no such request"})
            history = M.load_history()
            cand = block.candidates(req, history)
            rows = [{**c, "similarity_score": SIM.score(req, c)} for c in cand]
            return self._send(200, {"category": req["category"], "candidates": rows})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/check":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "body must be JSON"})
        rid = body.get("request_id")
        req = next((r for r in M.load_requests() if r["request_id"] == rid), None)
        if not req:
            return self._send(404, {"error": "no such request"})
        history = M.load_history()
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"request_id": rid, "per_candidate": [], "draft": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = M.check(cfg, req, history, thinking=adapters.THINKING_OFF)
        except Exception as exc:
            msg_txt = str(exc)
            for k in ("api_key", "base_url"):
                val = cfg.get(k)
                if val:
                    msg_txt = msg_txt.replace(val, "[%s]" % k.upper())
            return self._send(200, {"request_id": rid, "per_candidate": [], "draft": None,
                                    "note": msg_txt[:500]})
        return self._send(200, {
            "request_id": rid, "per_candidate": r["per_candidate"],
            "like_item_ids": r["like_item_ids"], "draft": r["draft"],
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

    n_requests = len(M.load_requests())
    print("cold-start-match UI  ->  http://127.0.0.1:%d" % a.port)
    print("  requests: %d   API_KEY: %s"
          % (n_requests, "set" if config.has_key(cfg) else "not set (the page still renders)"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
