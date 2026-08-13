#!/usr/bin/env python3
"""The local app. Three static files and a handful of JSON endpoints, on the standard library.

    python3 -m src.app            # then open http://127.0.0.1:8012

⚑ IT WORKS WITH NO KEY, AND THAT IS A HARD REQUIREMENT RATHER THAN A COURTESY. Everything except
one endpoint is pure code: cutting the stream into windows, collapsing repeated lines, detecting a
service that has gone silent, running the rule floor and re-counting the whole board at any
threshold are all computed locally. A forker who clones this and runs it sees the product working —
and sees the free floor's real ceiling — before deciding whether to spend anything. `/api/triage`
is the only endpoint that calls a model, it is reachable only by an explicit click, and it says
what it costs before it is pressed.

⚠︎ THE SHARED `.env` MEANS A BRAND-NEW KIT ALREADY HAS A LIVE KEY. Every kit under this repo root
inherits the root `.env`, so "there is no key configured yet" is a false assumption on a fresh kit
— touching a model endpoint spends money immediately. That has already cost two unauthorised calls
in this estate. `/api/status` reports `has_key` so the UI can show the state, and nothing calls a
model as a side effect of loading a page.

⚑ THE THRESHOLD IS RECOMPUTED IN THE BROWSER, FROM FACTS THE SERVER SENT. Each window ships its
error count, whether the keyword regex matched and which services fell silent — the three inputs
the free floor has — so dragging the slider re-decides all 123 windows with no request and no cost.
That is what makes the finding demonstrable rather than assertable: the reader moves the control
themselves and watches no setting get all six traps right.
"""
import http.server
import json
import os
import socketserver
import sys
import urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_windows                                    # noqa: E402
from src import config, decide, prompt as pr, rules, window as W               # noqa: E402

UI = os.path.join(HERE, "ui")
RESULTS = os.path.join(HERE, "results")
PORT = int(os.environ.get("PORT", "8012"))

_CACHE = {}


def corpus():
    """Cut once. The stream is 15,000 events and the cut is deterministic, so re-doing it per
    request would be paying for the same answer on every keystroke."""
    if "windows" not in _CACHE:
        wins, labels = load_windows()
        _CACHE["windows"], _CACHE["labels"] = wins, labels
        _CACHE["index"] = {w["id"]: i for i, w in enumerate(wins)}
    return _CACHE["windows"], _CACHE["labels"]


def window_rows(limit=None):
    """Every candidate window with the three facts the free floor decides on. No model, no cost."""
    wins, labels = corpus()
    idx = _CACHE["index"]
    cand = W.candidates(wins)
    by_lab = {r["id"]: r for r in labels}
    out = []
    for wid in sorted(cand):
        i = idx[wid]
        win = wins[i]
        c = W.counts(win)
        hits = rules.keyword_hits(win)
        silent = W.gone_silent(wins, i)
        lab = by_lab.get(wid, {})
        out.append({
            "id": wid, "start": win["start"], "label": lab.get("label"), "trap": lab.get("trap"),
            # The three inputs, shipped so the browser can re-decide without asking again.
            "loud": c["loud"], "warn": c["WARN"], "lines": c["lines"],
            "keyword": hits[0]["message"][:70] if hits else None,
            "silent": silent,
            "silent_history": {s: [sum(1 for e in wins[i - k]["events"] if e["service"] == s)
                                   for k in range(W.HISTORY, 0, -1)] for s in silent},
            "collapsed": W.collapse(win)[:24],
            "collapsed_total": len(W.collapse(win)),
        })
    # Loudest first — which is deliberately the WRONG order for this problem, and the app says so:
    # the two windows that matter most are near the bottom.
    out.sort(key=lambda r: -r["loud"])
    return out[:limit] if limit else out


def recorded():
    """Whatever runs are on disk. A kit with no run yet returns an empty list rather than an error —
    the app is the thing you look at BEFORE deciding to fire a run."""
    out = []
    if os.path.isdir(RESULTS):
        for name in sorted(os.listdir(RESULTS)):
            if name.endswith(".json") and name != "baseline.json":
                try:
                    out.append(json.load(open(os.path.join(RESULTS, name), encoding="utf-8")))
                except Exception:
                    continue
    return out


def baseline():
    path = os.path.join(RESULTS, "baseline.json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return None


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
            wins, labels = corpus()
            st = W.stats(wins, labels)
            base = baseline() or {}
            return self._json({
                "has_key": config.has_key(cfg), "model": cfg.get("model") or None,
                "provider": cfg.get("provider"), "verdicts": list(pr.VERDICTS),
                "verdict_means": pr.MEANS, "outcomes": list(decide.OUTCOMES),
                "outcome_means": decide.MEANS, "threshold": rules.DEFAULT_THRESHOLD,
                "window_seconds": W.WINDOW_S, "gate": st,
                "claim": base.get("claim"),
                "count_threshold_contributes": base.get("count_threshold_contributes"),
                "runs": [r.get("run_id") for r in recorded()],
                "cost_note": "Every Ask-the-model click is ONE model call on your key. Nothing "
                             "else here calls anything — the threshold, the tiles and every "
                             "window below are computed locally."})
        if path == "/api/windows":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            limit = int(q.get("limit", ["0"])[0]) or None
            return self._json({"windows": window_rows(limit), "gate": W.stats(*corpus())})
        if path == "/api/baseline":
            return self._json(baseline() or {"error": "no baseline yet — python3 -m evals.baseline"})
        if path == "/api/runs":
            return self._json({"runs": recorded()})
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/triage":
            return self._json({"error": "no such endpoint"}, 404)
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n) or "{}")
        wins, labels = corpus()
        wid = body.get("id")
        if wid not in _CACHE["index"]:
            return self._json({"error": "unknown window id"}, 400)
        i = _CACHE["index"][wid]
        from evals.run import prompt_for
        user, collapsed, silent = prompt_for(wins, i)
        cfg = config.load()
        if not config.has_key(cfg):
            # The honest failure: no key, so no call, and the free verdict is still returned.
            verdict, reasons = rules.decide_window(wins[i])
            return self._json({"error": "no API_KEY configured", "verdict": None,
                               "floor_verdict": verdict, "floor_reasons": reasons,
                               "prompt": user}, 400)
        from src.adapters import complete
        got = complete(cfg, pr.SYSTEM, user, max_tokens=pr.MAX_TOKENS)
        verdict = pr.parse(got["text"])
        floor_verdict, floor_reasons = rules.decide_window(wins[i])
        lab = next((r for r in labels if r["id"] == wid), {})
        return self._json({"verdict": verdict, "raw": got["text"],
                           "replied": verdict is not None,
                           "outcome": decide.outcome(lab.get("label"), verdict,
                                                     verdict is not None),
                           "floor_verdict": floor_verdict, "floor_reasons": floor_reasons,
                           "label": lab.get("label"), "trap": lab.get("trap"),
                           "prompt": user, "finish_reason": got.get("finish_reason"),
                           "input_tokens": got["input_tokens"],
                           "output_tokens": got["output_tokens"]})

    def log_message(self, fmt, *args):
        pass


def main():
    cfg = config.load()
    wins, labels = corpus()
    st = W.stats(wins, labels)
    print("ops-triage — http://127.0.0.1:%d" % PORT)
    print("  %d windows cut from %d events; %d pass the gate, all of it computed locally"
          % (len(wins), sum(len(w["events"]) for w in wins), st["candidates"]))
    print("  gate recall %.1f%% — every incident in the corpus survives it"
          % (100 * st["gate_recall"]))
    print("  key configured: %s%s" % (config.has_key(cfg),
                                      " (%s)" % cfg["model"] if cfg.get("model") else ""))
    print("  nothing calls a model until you press Ask the model, and that is one call per press.")
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
