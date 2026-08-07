"""Pull document PAIRS from the Federal Register API into data/_fetched/. Costs nothing, no key.

    python -m tools.fetch_corpus                  # the shipped corpus: up to 60 pairs
    python -m tools.fetch_corpus --pairs 10        # a smaller pull, for trying it out

⚑ A PAIR IS A RULE AND ITS OWN LATER CORRECTION, LINKED BY THE PUBLISHER'S OWN RIN — not by
parsing a citation out of a paragraph of prose. Every Federal Register document carries a
Regulation Identifier Number (RIN) that tracks one regulatory action through its lifecycle —
proposed rule, final rule, any correction — and the API can be searched BY it
(`conditions[regulation_id_number]=<RIN>`, verified live against the running API on 2026-08-06).
So the fetch is two clean queries: find corrections, then ask the API for everything sharing that
correction's RIN, rather than regexing "(91 FR 46000)" out of an abstract and hoping it matches.

⚠︎ `correction_of` AND `corrections`, THE FIELDS THAT SOUND LIKE THEY DO THIS, DO NOT. Checked live
on a document that is unambiguously a correction of another (2026-16049 corrects 2026-14790, said
in its own abstract): both fields returned empty on both documents. Whatever populates them is not
reliable enough to build a corpus on, so this file does not use them.

⚠︎ RAW PULLS ARE NOT SHIPPED. data/_fetched/ is gitignored — same rule as docs-route.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHED = os.path.join(HERE, "data", "_fetched")
API = "https://www.federalregister.gov/api/v1/documents.json"

FIELDS = ["document_number", "title", "abstract", "action", "type", "publication_date",
          "regulation_id_numbers", "html_url"]

PAUSE_SECONDS = 1.0
UA = "adhana-foundry-kits/docs-redline (https://github.com/adhana-ai/adhana-foundry-kits)"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _search(params):
    return _get(API + "?" + urllib.parse.urlencode(params, doseq=True))


def find_corrections(want, page_size=100):
    """Rule-type documents whose own `action` field says this IS a correction. `conditions[term]`
    is full-text search (fuzzy — it would also match a rule that merely MENTIONS a correction), so
    every hit is re-checked against its own `action` field before being kept."""
    found, page = [], 1
    while len(found) < want and page <= 20:
        params = [("per_page", str(page_size)), ("page", str(page)), ("order", "newest"),
                  ("conditions[type][]", "RULE"), ("conditions[term]", "correction")]
        params += [("fields[]", f) for f in FIELDS]
        payload = _search(params)
        results = payload.get("results") or []
        if not results:
            break
        for rec in results:
            action = (rec.get("action") or "").lower()
            if "correction" in action and rec.get("regulation_id_numbers"):
                found.append(rec)
        page += 1
        time.sleep(PAUSE_SECONDS)
    return found[:want]


def find_original(correction, rin):
    """The nearest earlier Rule sharing this RIN — the document the correction is fixing.
    'Nearest earlier' rather than 'first' because a RIN can carry several final rules across a
    regulation's life (an amendment, then an amendment to the amendment); the one a correction
    fixes is whichever Rule under that RIN was published most recently before it."""
    params = [("per_page", "50"), ("conditions[regulation_id_number]", rin)]
    params += [("fields[]", f) for f in FIELDS]
    payload = _search(params)
    candidates = [
        r for r in (payload.get("results") or [])
        if r.get("type") == "Rule"
        and r.get("document_number") != correction.get("document_number")
        and (r.get("publication_date") or "") < (correction.get("publication_date") or "")
        and "correction" not in (r.get("action") or "").lower()
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda r: r.get("publication_date") or "")
    return candidates[-1]


def fetch(want_pairs):
    os.makedirs(FETCHED, exist_ok=True)
    corrections = find_corrections(want_pairs * 2)     # over-fetch: not every one will pair
    print("  %d candidate correction(s) found, checking each for its earlier Rule…"
         % len(corrections))
    pairs = []
    for c in corrections:
        if len(pairs) >= want_pairs:
            break
        rins = c.get("regulation_id_numbers") or []
        original = None
        for rin in rins:
            original = find_original(c, rin)
            if original:
                break
            time.sleep(PAUSE_SECONDS)
        if original:
            pairs.append({"v1": original, "v2": c})
            print("  paired  %-14s -> %-14s  (%s)"
                 % (original["document_number"], c["document_number"], rins[0] if rins else "?"))
        time.sleep(PAUSE_SECONDS)

    path = os.path.join(FETCHED, "pairs.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pairs": pairs}, f, indent=1, ensure_ascii=False)
    print("\n-> %s" % os.path.relpath(path, HERE))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=60, help="how many pairs to try to fetch")
    a = ap.parse_args()
    print("fetching up to %d rule/correction pair(s) from the Federal Register API — "
         "no key, no cost" % a.pairs)
    pairs = fetch(a.pairs)
    print("\n%-30s %d" % ("pairs fetched", len(pairs)))
    print("\nNext: python -m tools.build_corpus")


if __name__ == "__main__":
    main()
