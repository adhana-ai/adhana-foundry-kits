"""The minimal local app — one of the four layers a kit is allowed.

⚑ IT RUNS ON 127.0.0.1 AND NOWHERE ELSE. This binds to loopback deliberately: the app executes
generated SQL against a database, and the one thing it must never become is a query endpoint
somebody else can reach. There is no auth here because there is nothing to authenticate — the
correct control is that the socket is not reachable, not a password on a demo.

⚑ IT RENDERS WITHOUT A KEY. `/api/results` reads the recorded run off disk, so a fresh clone shows
real measured output before anyone configures anything. A key is needed only to ask a NEW question.
That is what makes "clone it and see something true in ten minutes" a claim rather than a hope.

⚠︎ NO API KEY IS EVER REQUESTED FROM A READER, on any surface. `/api/connect` writes the FORKER's
own key into their own gitignored .env on their own machine. It is never transmitted anywhere by
this app, and the published kit page never asks for one.
"""
import argparse
import glob
import json
import os
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import config, execute as ex, guard, prompt as pr, schema   # noqa: E402

UI = os.path.join(HERE, "ui")
RESULTS = os.path.join(HERE, "results")
LABELS = os.path.join(HERE, "data", "labelled.jsonl")


def api_status():
    cfg = config.load()
    return {"has_key": config.has_key(cfg),
            "provider": cfg.get("provider"), "model": cfg.get("model"),
            "sources": [{"which": w, "path": p, "exists": e} for w, p, e in config.sources()],
            "tables": schema.stats(),
            "schema_card": schema.card(),
            "results_available": bool(glob.glob(os.path.join(RESULTS, "*.json")))}


def api_connect(body):
    """Write the forker's own connection into their own .env. Never leaves this machine."""
    keep = {k: v for k, v in body.items()
            if k in config.WRITABLE and isinstance(v, str) and v.strip()}
    if not keep:
        return {"ok": False, "error": "nothing to save"}
    path = config.save(keep)
    return {"ok": True, "saved": sorted(keep), "path": path,
            "has_key": config.has_key(config.load())}


def api_examples():
    """The labelled questions, so a reader can click one instead of inventing SQL to test."""
    rows = []
    with open(LABELS, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                rows.append({"id": r["id"], "question": r["question"],
                             "answerable": bool(r.get("gold_sql")), "tests": r.get("tests", "")})
    return {"examples": rows}


def api_ask(question):
    """The whole pipeline for one question: prompt -> model -> guard -> execute.

    Every stage's outcome is returned, including the stages that refused. A UI that only showed the
    rows would hide the two things this kit exists to show: the SQL, and the fact that it was
    checked before it ran.
    """
    if not question or not question.strip():
        return {"ok": False, "error": "ask something"}
    cfg = config.load()
    if not config.has_key(cfg):
        return {"ok": False, "needs_key": True,
                "error": "no API_KEY configured. The recorded run renders without one; asking a "
                         "new question needs your own key."}

    card = schema.card()
    system, user, parts = pr.assemble(question, card)
    out = {"ok": True, "question": question, "prompt_chars": len(user),
           "prompt_parts": [{"name": p["name"], "chars": len(p["text"])} for p in parts]}

    from src.adapters import complete, AdapterError
    t0 = time.time()
    try:
        got = complete(cfg, system, user)
    except AdapterError as exc:
        return {"ok": False, "error": str(exc)}
    out["model_ms"] = round((time.time() - t0) * 1000, 2)
    out["input_tokens"] = got["input_tokens"]
    out["output_tokens"] = got["output_tokens"]

    sql_text = pr.clean(got["text"])
    out["sql"] = sql_text

    if sql_text.strip().upper().startswith(pr.CANNOT):
        out["stage"] = "cannot_answer"
        out["message"] = ("The model reported that this schema cannot answer the question. That is "
                          "a correct outcome, not a failure — two of the labelled questions expect "
                          "exactly this.")
        return out

    ok, why = guard.check(sql_text)
    out["guard_ok"] = ok
    if not ok:
        out["stage"] = "refused"
        out["guard_reason"] = why
        out["message"] = "Nothing was executed. Your database is untouched."
        return out

    try:
        res = ex.run(sql_text)
    except ex.ExecError as exc:
        out["stage"] = "exec_error"
        out["error"] = str(exc)
        return out

    out["stage"] = "ok"
    out.update({"columns": res["columns"], "rows": res["rows"],
                "row_count": res["row_count"], "truncated": res["truncated"],
                "exec_ms": res["ms"]})
    return out


def api_results():
    """One card per RUN, never one per file.

    ⚠︎ THIS USED TO LIST EVERY FILE, AND THAT MISREPRESENTED THE KIT'S CENTRAL CLAIM. A re-scored
    run is a second FILE and the same run: same questions, same model, same statements, a corrected
    ruler. Listed side by side they rendered as "70%" and "80%" one above the other, which reads as
    two runs on a kit whose whole claim is `run once`. Grouping by run_id and folding the re-score
    into its parent is the difference between a correction and a second attempt.
    """
    files = sorted(glob.glob(os.path.join(RESULTS, "*.json")))
    if not files:
        return {"runs": [], "note": "No run recorded yet. `python3 evals/run.py --run-id <id>`."}
    by_run = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        rid = d.get("run_id") or os.path.basename(f)
        entry = by_run.setdefault(rid, {"run_id": rid, "model": d.get("model"),
                                        "files": [], "rescored": None})
        entry["files"].append(os.path.basename(f))
        # The re-scored file supersedes the raw one for the headline number, and says so.
        if d.get("rescored"):
            entry["rescored"] = d["rescored"]
            entry["summary"] = d.get("summary")
            entry["could_not_verify"] = d.get("could_not_verify", [])
        elif "summary" not in entry:
            entry["summary"] = d.get("summary")
            entry["could_not_verify"] = d.get("could_not_verify", [])
    return {"runs": list(by_run.values())}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def _send(self, code, body, ctype):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(UI, "index.html"), encoding="utf-8") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path in ("/app.js", "/app.css"):
            kind = "application/javascript" if u.path.endswith(".js") else "text/css"
            with open(os.path.join(UI, u.path.lstrip("/")), encoding="utf-8") as f:
                return self._send(200, f.read(), kind + "; charset=utf-8")
        if u.path == "/favicon.ico":
            # 204, not 404. Browsers request this unprompted and a red line in a fresh clone's
            # console is the kind of thing that reads as "the kit is broken" to someone who just
            # arrived. There is no icon to serve, and saying so quietly is the honest answer.
            self.send_response(204)
            self.end_headers()
            return
        if u.path == "/api/status":
            return self._json(api_status())
        if u.path == "/api/examples":
            return self._json(api_examples())
        if u.path == "/api/results":
            return self._json(api_results())
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"ok": False, "error": "bad JSON"}, 400)
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/ask":
            return self._json(api_ask(body.get("question", "")))
        if u.path == "/api/connect":
            return self._json(api_connect(body))
        return self._json({"error": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8010)
    a = ap.parse_args()
    if not os.path.exists(os.path.join(HERE, "data", "shop.db")):
        print("no database yet — building it")
        sys.path.insert(0, os.path.join(HERE, "tools"))
        import build_db
        build_db.build()
    cfg = config.load()
    print("data-qa on http://127.0.0.1:%d" % a.port)
    print("  tables : %s" % ", ".join("%s (%s)" % (t, "{:,}".format(n))
                                      for t, n in schema.stats().items()))
    print("  key    : %s" % ("configured" if config.has_key(cfg) else
                             "not configured — recorded results still render"))
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
