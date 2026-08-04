"""Pull raw study records from ClinicalTrials.gov into data/_fetched/.

WHAT THIS IS AND IS NOT. This writes the RAW API responses and nothing else. It is a separate step
from build_corpus.py on purpose: fetching touches the network and is not reproducible byte-for-byte
(the registry is edited daily), while building the shippable corpus from a fetch IS reproducible.
Keeping them apart means a forker can rebuild the exact corpus this kit ships without a network,
and can also go and pull a fresh one, and the two operations cannot be confused.

⚠︎ data/_fetched/ IS NEVER SHIPPED. The rule is the golden kit's and it is not negotiable here:
data/ ships the CORPUS, licensed for a public repo — never the raw pulls. .gitignore holds it.

WHY THIS SOURCE. Records are U.S. Government works and therefore public domain (17 U.S.C. §105),
which is the one legal landmine a public kit has to clear before anything else. It is also the
rare corpus that arrives with its own ground truth: the same record carries free narrative prose
AND the structured values behind it, so a gold set costs nothing and is not authored by us. On
UC001 the labelled set was the expensive part.

WHY A SPREAD OF CONDITIONS. Pulling 60 records about one disease would produce 60 documents that
phrase everything the same way, and per-field accuracy on that measures how well the model reads
one template. The conditions below are a deliberately mixed bag.
"""
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "_fetched")
API = "https://clinicaltrials.gov/api/v2/studies"

# Ten conditions, six studies each. Chosen to vary the writing, not to make a medical point.
CONDITIONS = ["diabetes", "asthma", "melanoma", "stroke", "epilepsy",
              "hypertension", "psoriasis", "migraine", "sepsis", "glaucoma"]
PER_CONDITION = 6


def fetch(condition, n):
    q = urllib.parse.urlencode({
        "query.cond": condition,
        "filter.overallStatus": "COMPLETED",
        "pageSize": str(n),
        "countTotal": "false",
    })
    req = urllib.request.Request(
        "%s?%s" % (API, q),
        # A contactable UA is basic manners against a public endpoint that costs someone money.
        headers={"User-Agent": "adhana-foundry-kits/docs-extract (public-domain corpus build)"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    os.makedirs(RAW, exist_ok=True)
    kept, seen = 0, set()
    for cond in CONDITIONS:
        try:
            page = fetch(cond, PER_CONDITION)
        except Exception as exc:
            # A failed condition is reported and skipped, never retried into a rate limit. The
            # corpus is smaller and the build says so; it does not silently substitute another.
            print("  !! %-12s %s" % (cond, exc))
            continue
        for st in page.get("studies", []):
            nct = (st.get("protocolSection", {}).get("identificationModule", {})
                     .get("nctId"))
            if not nct or nct in seen:
                continue
            seen.add(nct)
            with open(os.path.join(RAW, "%s.json" % nct), "w", encoding="utf-8") as f:
                json.dump(st, f, indent=1, ensure_ascii=False)
            kept += 1
        print("  %-12s %d record(s)" % (cond, len(page.get("studies", []))))
        time.sleep(0.4)                      # deliberate, unhurried; this is someone's free API
    print("fetch_corpus: %d record(s) -> %s" % (kept, os.path.relpath(RAW, HERE)))


if __name__ == "__main__":
    main()
