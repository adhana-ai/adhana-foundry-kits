"""Pull raw documents from the Federal Register API into data/_fetched/. Costs nothing, no key.

    python -m tools.fetch_corpus                  # the shipped corpus: 40 per routed type
    python -m tools.fetch_corpus --per-type 10    # a smaller pull, for trying it out

⚑ IT FETCHES PER CLASS, DELIBERATELY UNBALANCED-PROOF. The natural distribution of the Federal
Register is roughly 7 notices to 2 rules to 1 proposed rule — measured, 103/34/13 in a 150-document
sample of newest-first. A corpus drawn that way makes "answer Notice every time" score 69%, and
then every number the kit publishes is a fact about the sampling rather than about the router. So
each class is fetched on its own query and the shipped corpus is balanced by construction.

⚠︎ AND THAT IS A CHOICE WITH A COST, WHICH THE KIT STATES RATHER THAN HIDES. A balanced corpus is
NOT what arrives in a real inbox, so the precision figures here are not the precision you would
see in production — a class that is 10% of the eval set and 2% of reality will look far more
dangerous here than it is. The balanced set answers "can it tell these apart"; it does not answer
"what happens on Tuesday". Both questions are worth asking and only the first one fits in a kit.

⚑ RAW PULLS ARE NOT SHIPPED. data/_fetched/ is gitignored: it is the provider's payload, and what
belongs in a public repo is the corpus built from it, with its own manifest and licence. Same rule
as every kit here.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import taxonomy as TX                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHED = os.path.join(HERE, "data", "_fetched")
API = "https://www.federalregister.gov/api/v1/documents.json"

# The API's own code for each type this kit routes. Keyed by queue so the mapping is stated once
# and read from taxonomy.ORDER — adding a class cannot leave the fetcher silently behind.
TYPE_CODE = {"rule": "RULE", "proposed": "PRORULE", "notice": "NOTICE"}

FIELDS = ["document_number", "title", "abstract", "type", "publication_date",
          "agencies", "html_url", "action"]

# One request per class, and a pause between them. The Federal Register asks for a courteous rate
# and gives no published quota; three requests total is already courteous, and the sleep is here
# so that raising --per-type never turns this into a hammer.
PAUSE_SECONDS = 1.0


def _get(url):
    req = urllib.request.Request(url, headers={
        # A real contact string rather than a browser lie. The API's terms ask that automated
        # callers identify themselves, and a kit that ships a fake User-Agent teaches that.
        "User-Agent": "adhana-foundry-kits/docs-route (https://github.com/adhana-ai/adhana-foundry-kits)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch(per_type):
    os.makedirs(FETCHED, exist_ok=True)
    written = {}
    for queue in TX.ORDER:
        params = [("per_page", str(min(per_type, 1000))), ("order", "newest"),
                  ("conditions[type][]", TYPE_CODE[queue])]
        params += [("fields[]", f) for f in FIELDS]
        url = API + "?" + urllib.parse.urlencode(params)
        payload = _get(url)
        path = os.path.join(FETCHED, "%s.json" % queue)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, ensure_ascii=False)
        got = payload.get("results") or []
        written[queue] = len(got)
        print("  %-10s %3d document(s) -> %s" % (TX.label_of(queue), len(got),
                                                 os.path.relpath(path, HERE)))
        time.sleep(PAUSE_SECONDS)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=40,
                    help="how many documents to pull per routed type (default 40)")
    a = ap.parse_args()
    print("fetching %d document(s) per type from the Federal Register API — no key, no cost"
          % a.per_type)
    written = fetch(a.per_type)
    print("\n%-30s %d" % ("types fetched", len(written)))
    print("%-30s %d" % ("documents fetched", sum(written.values())))
    print("\nNext: python -m tools.build_corpus")


if __name__ == "__main__":
    main()
