"""The minimal local UI. Standard library only — python -m src.app, then open the printed URL.

WHAT IT IS FOR. One message, one match-and-impact call, on your machine, with your key. It is the
proof that this runs on a laptop and it is the only thing in the kit that starts a process. It is
NOT the published dashboard: the boards that grade the run live in the Foundry site, from
committed run records.

IT RENDERS WITH NO KEY. /api/state, /api/message and /api/candidates need nothing; only
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

from src import config, block, match as M                    # noqa: E402
from src import adapters                                       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port; see sibling kits' src/app.py headers for the rest of the range.
PORT = int(os.environ.get("PORT", "8781"))


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
            return self._send(200, {"messages": [m["message_id"] for m in M.load_messages()],
                                    "has_key": config.has_key()})
        if u.path == "/api/message":
            mid = (parse_qs(u.query).get("id") or [""])[0]
            match_msg = next((m for m in M.load_messages() if m["message_id"] == mid), None)
            if not match_msg:
                return self._send(404, {"error": "no such message"})
            return self._send(200, match_msg)
        if u.path == "/api/candidates":
            mid = (parse_qs(u.query).get("id") or [""])[0]
            msg = next((m for m in M.load_messages() if m["message_id"] == mid), None)
            if not msg:
                return self._send(404, {"error": "no such message"})
            v = M.vendors_by_id()[msg["vendor_id"]]
            blocked = block.candidates(msg, v, M.records_by_vendor_sku())
            return self._send(200, {"vendor": v["name"], "candidates": blocked["candidates"]})
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
        mid = req.get("message_id")
        msg = next((m for m in M.load_messages() if m["message_id"] == mid), None)
        if not msg:
            return self._send(404, {"error": "no such message"})
        v = M.vendors_by_id()[msg["vendor_id"]]
        vsku = M.records_by_vendor_sku()
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"message_id": mid, "match": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = M.check(cfg, msg, v, vsku, thinking=adapters.THINKING_OFF)
        except Exception as exc:
            msg_txt = str(exc)
            for k in ("api_key", "base_url"):
                val = cfg.get(k)
                if val:
                    msg_txt = msg_txt.replace(val, "[%s]" % k.upper())
            return self._send(200, {"message_id": mid, "match": None, "note": msg_txt[:500]})
        return self._send(200, {
            "message_id": mid, "candidates": r["candidates"], "match": r["match"],
            "change_type": r["change_type"], "new_value": r["new_value"],
            "citation": r["citation"], "computed_impact": r["computed_impact"],
            "decision": r["decision"],
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

    n_messages = len(M.load_messages())
    print("change-impact UI  ->  http://127.0.0.1:%d" % a.port)
    print("  messages: %d   API_KEY: %s"
          % (n_messages, "set" if config.has_key(cfg) else "not set (the page still renders)"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
