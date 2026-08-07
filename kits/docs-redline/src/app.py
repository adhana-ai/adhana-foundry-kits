"""The minimal local UI. Standard library only — python -m src.app, then open the printed URL.

WHAT IT IS FOR — same as docs-route's: one pair, one verdict, on your machine, with your key. It
is the proof that this runs on a laptop, not the published board.

IT RENDERS WITH NO KEY. /api/levels, /api/pair and /api/baseline need nothing — the alignment
step and the regex baseline are both pure code. Only /api/classify calls a provider.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, redline as RL, materiality as MT, diff as D  # noqa: E402
from evals import baseline as B                                      # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port: docs-qa 8765, docs-extract 8766, docs-summarise 8767, docs-route 8768.
PORT = int(os.environ.get("PORT", "8769"))


def _pair_by_id(pair_id):
    for pid, v1, v2 in RL.pairs():
        if pid == pair_id:
            return v1, v2
    return None, None


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
        if u.path == "/api/levels":
            cfg = config.load()
            return self._send(200, {
                "levels": [{"key": k, "label": MT.label_of(k), "meaning": MT.meaning(k)}
                          for k in MT.ORDER],
                "abstain": MT.ABSTAIN,
                "floor": RL.CONFIDENCE_FLOOR,
                "pairs": [p[0] for p in RL.pairs()],
                "model": cfg.get("model"),
                "has_key": config.has_key(cfg),
            })
        if u.path == "/api/pair":
            pid = (parse_qs(u.query).get("id") or [""])[0]
            v1_id, v2_id = _pair_by_id(pid)
            if v1_id is None:
                return self._send(404, {"error": "no such pair"})
            v1_text, v2_text = RL.load_version(v1_id), RL.load_version(v2_id)
            return self._send(200, {"pair_id": pid, "v1_id": v1_id, "v2_id": v2_id,
                                    "v1_text": v1_text, "v2_text": v2_text,
                                    "span": D.primary(v1_text, v2_text)})
        if u.path == "/api/baseline":
            pid = (parse_qs(u.query).get("id") or [""])[0]
            v1_id, v2_id = _pair_by_id(pid)
            if v1_id is None:
                return self._send(404, {"error": "no such pair"})
            span = D.primary(RL.load_version(v1_id), RL.load_version(v2_id))
            if span is None:
                return self._send(200, {"pair_id": pid, "materiality": None, "state": "no_change"})
            pred = B.regex_predict(span)
            return self._send(200, {"pair_id": pid, "materiality": pred["materiality"],
                                    "state": pred["state"], "rule": pred.get("rule")})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/classify":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        pid = body.get("id")
        v1_id, v2_id = _pair_by_id(pid)
        if v1_id is None:
            return self._send(404, {"error": "no such pair"})
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"pair_id": pid, "no_key": True,
                                    "message": "No API_KEY configured, so no model was called. "
                                               "The regex baseline above needs no key and is "
                                               "the thing a model has to beat."})
        try:
            rec = RL.decide(cfg, RL.load_version(v1_id), RL.load_version(v2_id),
                            floor=body.get("floor", RL.CONFIDENCE_FLOOR))
        except Exception as exc:
            return self._send(200, {"pair_id": pid, "error": "%s: %s" % (type(exc).__name__, exc)})
        rec["pair_id"] = pid
        rec["outcome"] = RL.outcome(rec)
        return self._send(200, rec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()
    cfg = config.load()
    print("docs-redline — %d pair(s), %d level(s), floor %.2f"
         % (len(RL.pairs()), len(MT.ORDER), RL.CONFIDENCE_FLOOR))
    print("model: %s   key configured: %s"
         % (cfg.get("model") or "(none set)", "yes" if config.has_key(cfg) else "no"))
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise SystemExit("port %d is already in use — another kit's app is probably running. "
                             "Try: python -m src.app --port %d" % (a.port, a.port + 10))
        raise
    print("open http://127.0.0.1:%d" % a.port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
