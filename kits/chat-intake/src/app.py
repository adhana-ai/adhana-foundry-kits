#!/usr/bin/env python3
"""The local UI. One page, no framework, stdlib http.server.

    python3 -m src.app            ->  http://127.0.0.1:8769

⚑ IT RUNS WITH NO KEY, AND SAYS SO. Without a key the page still shows the checklist, the states
and a real conversation stepping forward turn by turn, with the collection driven by the dataset's
own dialogue state instead of by a model. That is labelled REPLAY everywhere it appears — it is the
corpus telling you what was established, not a prediction — because a demo that looks like a model
run and is not is the worst thing a kit can ship.

⚠︎ AND IT NEEDS THE CORPUS FETCHED FIRST, WHICH IS NEW FOR THIS KIT. Every sibling ships its corpus
and works on a fresh clone offline. This one cannot: SGD is CC BY-SA 4.0 and this repo is MIT, so
the conversations are fetched, never committed. The page says exactly that, with the two commands,
rather than rendering an empty shell.
"""
import http.server
import json
import os
import socketserver
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, intake, slots                                        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")
GOLD = os.path.join(HERE, "data", "gold.jsonl")
PORT = int(os.environ.get("PORT", "8769"))


def _cases(limit=150):
    """Conversations to step through, one entry each, in a stable order.

    ⚠︎ SORT FIRST, THEN CAP — IT USED TO CAP FIRST AND THAT MADE THE PICKER LOOK SORTED WHILE BEING
    FILE ORDER. The tail was whatever shard happened to be read first, so `39_00123` — the one case
    both models are known to get wrong — was absent from a list that ended at `40_00003` and
    therefore looked complete. tools/shoot_ui.mjs selected it, the select silently no-opped, and
    the "failure" screenshot came out a success on a different conversation. A cap applied before
    a sort is a sample pretending to be a prefix.
    """
    if not os.path.exists(GOLD):
        return []
    seen, out = set(), []
    for line in open(GOLD, encoding="utf-8"):
        c = json.loads(line)
        if c["dialogue_id"] in seen:
            continue                      # one entry per conversation in the picker
        seen.add(c["dialogue_id"])
        out.append({"dialogue_id": c["dialogue_id"], "intent": c["intent"],
                    "opening": c["turns"][0]["utterance"] if c["turns"] else ""})
    return sorted(out, key=lambda c: c["dialogue_id"])[:limit]


def _conversation(dialogue_id):
    """Every prefix of one conversation, longest first in the file, returned shortest first."""
    rows = []
    for line in open(GOLD, encoding="utf-8"):
        c = json.loads(line)
        if c["dialogue_id"] == dialogue_id:
            rows.append(c)
    return sorted(rows, key=lambda c: len(c["turns"]))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=UI, **kw)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/state":
            built = os.path.exists(GOLD) and os.path.exists(slots.PATH)
            return self._json({
                "built": built,
                "has_key": config.has_key(),
                "checklist": slots.intents() if os.path.exists(slots.PATH) else {},
                "states": slots.states() if os.path.exists(slots.PATH) else [],
                "cases": _cases() if built else [],
                "build_with": ["python3 -m tools.fetch_corpus", "python3 -m tools.build_corpus"],
            })
        if self.path.startswith("/api/conversation/"):
            did = self.path.rsplit("/", 1)[-1]
            rows = _conversation(did)
            if not rows:
                return self._json({"error": "no such conversation"}, 404)
            return self._json({
                "dialogue_id": did,
                "intent": rows[0]["intent"],
                "required": slots.required(rows[0]["intent"]),
                # Each step is a prefix and the gold state at its end. `replay` is the dataset's
                # own answer; the model's answer arrives from /api/turn and sits beside it.
                "steps": [{"turns": r["turns"], "replay": r["gold_slots"],
                           "complete": r["gold_complete"], "case_id": r["case_id"]}
                          for r in rows],
            })
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/turn":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or b"{}")
        cfg = config.load()
        if not config.has_key(cfg):
            return self._json({"error": "no API_KEY configured — the page runs in replay without "
                                        "one, which is what you are seeing"}, 400)
        try:
            # `unparsed_before` comes from the caller because this server holds no state between
            # requests — the same reason the whole conversation prefix arrives in the body.
            out = intake.turn(cfg, req["intent"], req["turns"],
                              unparsed_before=req.get("unparsed_before") or 0)
        except Exception as exc:                       # noqa: BLE001 — surfaced, never swallowed
            return self._json({"error": "%s: %s" % (type(exc).__name__, exc)}, 502)
        out["next_question"] = intake.next_question(req["intent"], out["missing"],
                                                    escalate=out["escalate"])
        if out.get("budget_exhausted"):
            # Named on the surface a person is looking at, because "no answer" and
            # "the answer was cut off mid-thought and billed in full" are different
            # events and only one of them is worth paging somebody about.
            out["notice"] = ("The reply hit the token ceiling and returned nothing. "
                             "This call was billed in full. Repeated on the same turn, "
                             "it is the signature of a hostile input.")
        out.pop("prompt", None)                        # the UI does not need it; the eval prints it
        return self._json(out)


def main():
    cfg = config.load()
    print("chat-intake  ->  http://127.0.0.1:%d" % PORT)
    print("  corpus built : %s" % ("yes" if os.path.exists(GOLD) else
                                   "NO — run tools.fetch_corpus then tools.build_corpus"))
    print("  API key      : %s" % ("configured" if config.has_key(cfg) else
                                   "none — the page runs in replay, labelled as replay"))
    for kind, path, present in config.sources():
        print("  %-12s : %s%s" % (kind, path, "" if present else "  (absent, which is fine)"))
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
