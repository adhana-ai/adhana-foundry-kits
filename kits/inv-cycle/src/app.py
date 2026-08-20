"""The minimal local UI. Standard library only -- python -m src.app, then open the printed URL.

WHAT IT IS FOR. One variance event, one drafting call, on your machine, with your key. It is the
proof that this runs on a laptop. It is NOT the published dashboard: the boards that grade the
full run live on the Foundry site, from committed run records.

IT RENDERS WITH NO KEY. /api/state and /api/event need nothing -- they show the item/location's
own transaction history log and the variance, both computed at build time. Only /api/draft calls a
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

from src import brief as B, config, pack as PACK, segment as SEG          # noqa: E402
from src import adapters                                                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port; see sibling kits' src/app.py headers for the rest of the range.
PORT = int(os.environ.get("PORT", "8791"))

_CACHE = {}


def _corpus():
    if "events" not in _CACHE:
        _CACHE["events"] = B.events()
        _CACHE["gold"] = B.gold_by_id()
    return _CACHE["events"], _CACHE["gold"]


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
        events, gold = _corpus()
        if u.path == "/api/state":
            return self._send(200, {"events": [e["event_id"] for e in events],
                                    "has_key": config.has_key()})
        if u.path == "/api/event":
            eid = (parse_qs(u.query).get("id") or [""])[0]
            e = next((x for x in events if x["event_id"] == eid), None)
            if not e:
                return self._send(404, {"error": "no such event"})
            packed, meta = PACK.pack(e)
            return self._send(200, {"event": e, "packed": packed, "pack_meta": meta})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/draft":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "body must be JSON"})
        eid = req.get("event_id")
        events, gold = _corpus()
        e = next((x for x in events if x["event_id"] == eid), None)
        if not e:
            return self._send(404, {"error": "no such event"})
        cfg = config.load()
        if not config.has_key(cfg):
            return self._send(200, {"event_id": eid, "answer": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            r = B.draft(cfg, e, thinking=adapters.THINKING_OFF)
        except Exception as exc:
            msg_txt = str(exc)
            for k in ("api_key", "base_url"):
                val = cfg.get(k)
                if val:
                    msg_txt = msg_txt.replace(val, "[%s]" % k.upper())
            return self._send(200, {"event_id": eid, "answer": None, "note": msg_txt[:500]})

        # ⚑ THE CITATION-VALIDITY CHECK RUNS HERE, ON EVERY LIVE DRAFT, NOT ONLY IN evals/run.py.
        # A reader of the UI sees a fabrication flagged the same second the model returns one --
        # the guardrail is not something that only shows up after the fact in a committed eval
        # result. Uses the identical predicate evals/scoring.py grades the real run with, so the
        # UI and the published board can never quietly disagree about what counts as fabricated.
        answer = dict(r["answer"])
        cause = answer.get("cause")
        citations = answer.get("citations") or []
        if cause and cause != "unresolved":
            answer["citation_ok"] = bool(citations) and all(
                SEG.line_supports_cause(e, i, cause) for i in citations)
        else:
            answer["citation_ok"] = None          # not applicable -- cause is 'unresolved'

        return self._send(200, {
            "event_id": eid, "answer": answer,
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

    events, _ = _corpus()
    print("inv-cycle UI  ->  http://127.0.0.1:%d" % a.port)
    print("  events: %d   API_KEY: %s"
          % (len(events), "set" if config.has_key(cfg) else "not set (the page still renders)"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
