"""The minimal local UI. Standard library only — python -m src.app, then open the printed URL.

WHAT IT IS FOR. One document, one brief, on your machine, with your key. It is the proof that this
runs on a laptop and it is the only thing in the kit that starts a process. It is NOT the published
dashboard: the boards that grade the run live in the Foundry site, from committed run records.

IT RENDERS WITH NO KEY. /api/rubric and /api/doc need nothing; only /api/summarise calls a
provider, and with no API_KEY it returns a 200 saying so rather than an error, so the page is
explorable before anyone spends anything.

⚠︎ AND IT DOES NOT OFFER TO GRADE. Every other control here is free; grading is a person reading
six sections against a weighted rubric, which is the kit's actual cost unit (reviewer-minutes) and
belongs in `python -m evals.grade`, where it can be recorded. A "Grade" button on this page would
imply the browser could produce the number, and the entire point of this use case is that it
cannot.
"""
import argparse
import errno
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import adapters, config, summarise as SM          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(HERE, "ui")

# One kit per port: docs-qa is 8765, docs-extract is 8766. Starting the third kit while the other
# two are up must not die with a nine-line traceback ending in "Address already in use", which
# reads as a broken kit rather than an occupied socket.
PORT = int(os.environ.get("PORT", "8767"))


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass                                    # the console is for the kit's output, not access logs

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(UI, "index.html"), "rb").read(),
                              "text/html; charset=utf-8")
        if u.path in ("/app.js", "/app.css"):
            ct = "text/javascript" if u.path.endswith(".js") else "text/css"
            return self._send(200, open(os.path.join(UI, u.path[1:]), "rb").read(),
                              ct + "; charset=utf-8")
        if u.path == "/api/rubric":
            r = SM.load_rubric()
            return self._send(200, {"sections": r["sections"], "scale": r["scale"],
                                    "documents": SM.documents(),
                                    "has_key": config.has_key()})
        if u.path == "/api/doc":
            did = (parse_qs(u.query).get("id") or [""])[0]
            if did not in SM.documents():
                return self._send(404, {"error": "no such document"})
            text = SM.load_doc(did)
            return self._send(200, {"id": did, "chars": len(text), "text": text})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/summarise":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "body must be JSON"})
        did = req.get("id")
        if did not in SM.documents():
            return self._send(404, {"error": "no such document"})
        cfg = config.load()
        if not config.has_key(cfg):
            # 200, not an error: "no key" is a configuration state the page should render calmly.
            return self._send(200, {"id": did, "sections": None,
                                    "note": "No API_KEY is configured, so nothing was called. "
                                            "Copy .env.example to .env and set one."})
        try:
            # ⚠︎ THINKING IS EXPLICITLY DISABLED HERE, NOT LEFT AT THE PROVIDER DEFAULT — and the
            # reason is that THIS KIT'S PUBLISHED NUMBERS COME FROM A THINKING-OFF RUN. The spec
            # cites `r005-nothink` and states `settings.thinking = "disabled"`; this line never
            # passed the argument, so every live click through this page ran with the provider
            # default instead and could not reproduce the page it sits behind.
            #
            # Found 2026-08-08 by checking all five already-published kits after docs-redact hit
            # the same defect. It is real HERE and nowhere else: docs-qa, docs-extract, docs-route
            # and docs-redline all publish from runs that also used the provider default, so their
            # apps and their pages already agree. The rule is not "always disable thinking" — it
            # is "the live UI runs what the published run ran".
            r = SM.summarise(cfg, SM.load_doc(did), SM.sections_spec(),
                             thinking=adapters.THINKING_OFF)
        except Exception as exc:
            # ⚠︎ THE PROVIDER'S MESSAGE IS RETURNED, THE CONFIGURATION IS NOT. A base URL or a key
            # can hold anything, so no secret's VALUE reaches the page, not even inside an error.
            msg = str(exc)
            for k in ("api_key", "base_url"):
                v = cfg.get(k)
                if v:
                    msg = msg.replace(v, "[%s]" % k.upper())
            return self._send(200, {"id": did, "sections": None, "note": msg[:500]})
        # ⚑ AN UNREADABLE REPLY IS SAID OUT LOUD, NOT RENDERED AS SIX SKIPPED SECTIONS.
        #
        # Found on this kit's very first live call, 2026-08-04. The reply did not parse, `parse()`
        # correctly returned {}, and every section came back state="missing" — so the panel drew
        # six cards reading "no such section in the reply" and nothing anywhere said the model's
        # whole answer had been unreadable. That is precisely the distinction this kit is built to
        # make, broken in the kit's own app: "the model declined" and "the reply was garbage" are
        # different facts, and one of them is not about the model at all.
        #
        # The eval harness already got this right — it records the failure with the output-token
        # count and keeps the raw text, because UC002 paid for discarding exactly that evidence.
        # The app was the reader that had not been taught.
        note = None
        if not r.get("parsed", True):
            n = r.get("output_tokens") or 0
            note = ("The model's reply could not be read as JSON, so no section was filled. "
                    "This is a parsing failure, not six refusals. It produced %d output tokens "
                    "against a ceiling of %d%s." %
                    (n, SM.MAX_TOKENS,
                     " — it hit the ceiling and was cut off mid-reply" if n >= SM.MAX_TOKENS
                     else ""))
        return self._send(200, {"id": did, "sections": r["sections"], "pack": r["pack"],
                                "segment_coverage": r["segment_coverage"],
                                "parsed": r.get("parsed", True), "note": note,
                                "input_tokens": r["input_tokens"],
                                "output_tokens": r["output_tokens"]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT,
                    help="default %d. The PORT environment variable works too." % PORT)
    a = ap.parse_args()

    cfg = config.load()
    # Bind first, announce second: anything that prints a promise before keeping it can print a
    # false one, and "UI -> http://..." followed by a traceback is exactly that.
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            "Port %d is already in use.\n"
            "\n"
            "Most likely that is another kit's UI — docs-qa defaults to 8765, docs-extract to\n"
            "8766. They can all run at once; they just need different ports.\n"
            "\n"
            "  python -m src.app --port %d          # or: PORT=%d python -m src.app\n"
            "\n"
            "To see what is holding it:  lsof -nP -iTCP:%d -sTCP:LISTEN"
            % (a.port, a.port + 1, a.port + 1, a.port))

    secs = SM.sections_spec()
    print("docs-summarise UI  ->  http://127.0.0.1:%d" % a.port)
    print("  documents: %d   brief sections: %d (weights total %d)   API_KEY: %s"
          % (len(SM.documents()), len(secs), sum(s["weight"] for s in secs),
             "set" if config.has_key(cfg) else "not set (the page still renders)"))


    srv.serve_forever()


if __name__ == "__main__":
    main()
