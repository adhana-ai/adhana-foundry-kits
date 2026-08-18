"""The minimal local UI. Standard library only — python -m src.app, then open the printed URL.

WHAT IT IS FOR. One order, one reconcile call, on your machine, with your key. It is the proof
that this runs on a laptop and it is the only thing in the kit that starts a process. It is NOT
the published dashboard: the boards that grade the run live in the Foundry site, from committed
run records.

IT RENDERS WITH NO KEY. /api/orders and /api/agreement need nothing; only /api/check calls a
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

from src import config, reconcile as R                      # noqa: E402
from src import adapters                                     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port; see sibling kits' src/app.py headers for the rest of the range.
PORT = int(os.environ.get("PORT", "8774"))


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
            return self._send(200, {"orders": [o["order_id"] for o in R.orders()],
                                    "has_key": config.has_key()})
        if u.path == "/api/order":
            order_id = (parse_qs(u.query).get("id") or [""])[0]
            match = next((o for o in R.orders() if o["order_id"] == order_id), None)
            if not match:
                return self._send(404, {"error": "no such order"})
            return self._send(200, match)
        if u.path == "/api/agreement":
            supplier_id = (parse_qs(u.query).get("supplier_id") or [""])[0]
            try:
                text = R.load_agreement(supplier_id)
            except OSError:
                return self._send(404, {"error": "no such supplier"})
            return self._send(200, {"supplier_id": supplier_id, "text": text})
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
        order_id = req.get("order_id")
        match = next((o for o in R.orders() if o["order_id"] == order_id), None)
        if not match:
            return self._send(404, {"error": "no such order"})
        agreement_text = R.load_agreement(match["supplier_id"])
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"order_id": order_id, "checks": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = R.check(cfg, match, agreement_text, thinking=adapters.THINKING_OFF)
        except Exception as exc:
            msg = str(exc)
            for k in ("api_key", "base_url"):
                v = cfg.get(k)
                if v:
                    msg = msg.replace(v, "[%s]" % k.upper())
            return self._send(200, {"order_id": order_id, "checks": None, "note": msg[:500]})
        return self._send(200, {
            "order_id": order_id,
            "checks": r["checks"],
            "summary": R.summary(r),
            "answered": r["answered"], "asked": r["asked"], "parsed": r["parsed"],
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

    n_orders = len(R.orders())
    print("data-reconcile UI  ->  http://127.0.0.1:%d" % a.port)
    print("  orders: %d   API_KEY: %s"
          % (n_orders, "set" if config.has_key(cfg) else "not set (the page still renders)"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
