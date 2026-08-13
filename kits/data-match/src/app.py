#!/usr/bin/env python3
"""The local app. Four static files and a handful of JSON endpoints, on the standard library.

    python3 -m src.app            # then open http://127.0.0.1:8011

⚑ IT WORKS WITH NO KEY, AND THAT IS A HARD REQUIREMENT RATHER THAN A COURTESY. Everything except one
endpoint is pure code: the candidate pairs, the similarity scores, the field-by-field agreement and the
whole threshold sweep are computed locally, so a forker who clones this and runs it sees the product
working before they have decided whether to spend anything. `/api/judge` is the only endpoint that calls
a model, it is only reachable by an explicit click, and it says what it will cost before it is pressed.

⚠︎ THE SHARED `.env` MEANS A BRAND-NEW KIT ALREADY HAS A LIVE KEY. Every kit under this repo root
inherits the root `.env`, so "there is no key configured yet" is a false assumption on a fresh kit —
touching a model endpoint spends money immediately. That has already cost two unauthorised calls in this
estate. `/api/status` reports `has_key` so the UI can show the state, and nothing calls a model as a side
effect of loading a page.
"""
import http.server
import json
import os
import socketserver
import sys
import urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_labels, load_records                        # noqa: E402
from src import block, config, decide, prompt as pr, similarity                # noqa: E402

UI = os.path.join(HERE, "ui")
RESULTS = os.path.join(HERE, "results")
PORT = int(os.environ.get("PORT", "8011"))
DEFAULT_THRESHOLD = 0.70


def pair_rows(limit=None):
    """Every candidate pair with its free score and its field detail. No model, no key, no cost."""
    records, labels = load_records(), load_labels()
    truth = {(min(p["a"], p["b"]), max(p["a"], p["b"])): p for p in labels}
    out = []
    for a, b in block.candidates(list(records.values())):
        cmp = similarity.compare(records[a], records[b])
        lab = truth.get((a, b))
        out.append({"a": records[a], "b": records[b], "score": cmp["score"],
                    "fields": cmp["fields"], "agreed": cmp["agreed"],
                    "label": (lab or {}).get("label"), "trap": (lab or {}).get("trap"),
                    "pair_id": (lab or {}).get("id")})
    out.sort(key=lambda r: -r["score"])
    return out[:limit] if limit else out


def recorded():
    """Whatever runs are on disk. A kit with no run yet returns an empty list rather than an error —
    the app is the thing you look at BEFORE deciding to fire a run."""
    out = []
    if os.path.isdir(RESULTS):
        for name in sorted(os.listdir(RESULTS)):
            if name.endswith(".json"):
                try:
                    out.append(json.load(open(os.path.join(RESULTS, name), encoding="utf-8")))
                except Exception:
                    continue
    return out


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=UI, **kw)

    def _json(self, payload, code=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/status":
            cfg = config.load()
            return self._json({
                "has_key": config.has_key(cfg), "model": cfg.get("model") or None,
                "provider": cfg.get("provider"), "verdicts": list(pr.VERDICTS),
                "verdict_means": pr.MEANS, "outcomes": list(decide.OUTCOMES),
                "outcome_means": decide.MEANS, "threshold": DEFAULT_THRESHOLD,
                "runs": [r.get("run_id") for r in recorded()],
                # Stated, not implied: the UI prints this so nobody has to guess what a click costs.
                "cost_note": "Every /api/judge click is ONE model call on your key. Nothing else here "
                             "calls anything."})
        if path == "/api/pairs":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            limit = int(q.get("limit", ["40"])[0])
            return self._json({"pairs": pair_rows(limit),
                               "blocking": block.stats(list(load_records().values()),
                                                       load_labels())})
        if path == "/api/sweep":
            rows = [{"label": r["label"], "score": r["score"]}
                    for r in pair_rows() if r["label"]]
            return self._json({"sweep": decide.sweep(rows), "pairs": len(rows)})
        if path == "/api/runs":
            return self._json({"runs": recorded()})
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/judge":
            return self._json({"error": "no such endpoint"}, 404)
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n) or "{}")
        records = load_records()
        a, b = records.get(body.get("a")), records.get(body.get("b"))
        if not a or not b:
            return self._json({"error": "unknown record id"}, 400)
        cfg = config.load()
        if not config.has_key(cfg):
            # The honest failure: no key, so no call, and the free score is still returned.
            return self._json({"error": "no API_KEY configured", "verdict": None,
                               "score": similarity.score(a, b)}, 400)
        from src.adapters import complete
        user = pr.render(a, b)
        got = complete(cfg, pr.SYSTEM, user, max_tokens=pr.MAX_TOKENS)
        verdict = pr.parse(got["text"])
        cmp = similarity.compare(a, b)
        return self._json({"verdict": verdict, "raw": got["text"], "score": cmp["score"],
                           "replied": verdict is not None, "prompt": user,
                           "merges": decide.merges(cmp["score"], DEFAULT_THRESHOLD, verdict),
                           "input_tokens": got["input_tokens"],
                           "output_tokens": got["output_tokens"]})

    def log_message(self, fmt, *args):
        pass


def main():
    cfg = config.load()
    print("data-match — http://127.0.0.1:%d" % PORT)
    print("  records %d, candidate pairs %d, all of it computed locally"
          % (len(load_records()), len(block.candidates(list(load_records().values())))))
    print("  key configured: %s%s" % (config.has_key(cfg),
                                      " (%s)" % cfg["model"] if cfg.get("model") else ""))
    print("  nothing calls a model until you press Judge, and that is one call per press.")
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
