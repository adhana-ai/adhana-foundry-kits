"""Pull raw GAO report text into data/_fetched/. Network step, separate from building on purpose.

WHAT THIS IS AND IS NOT. This writes the RAW text renditions and nothing else. Fetching touches
the network and is not reproducible byte-for-byte; building the shippable corpus from a fetch IS.
Keeping them apart means a forker can rebuild the exact corpus this kit ships without a network,
and can also go and pull a fresh one, and the two operations cannot be confused.

⚠︎ data/_fetched/ IS NEVER SHIPPED. data/ ships the CORPUS, licensed for a public repo — never the
raw pulls. .gitignore holds it.

WHY THIS SOURCE. GAO reports are U.S. Government works and therefore public domain
(17 U.S.C. §105) — the one legal landmine a public kit has to clear before anything else. They are
also the right SHAPE for this use case in a way most permissive corpora are not: 40-80 pages of
analytic prose with findings, figures and recommendations in it, across subjects from IT to health
to disaster recovery, which is what keeps a cross-domain kit cross-domain.

⚑ WHY api.govinfo.gov AND NOT gao.gov — MEASURED 2026-08-04, NOT ASSUMED.
The obvious source is gao.gov itself. It answers 403 to automated requests: the product page, the
asset PDF and the site's own search endpoint all refused with an Akamai "Access Denied" body under
a plain, honestly-identified User-Agent. Getting past that would mean impersonating a browser,
which is not a thing a public kit should teach anyone to do to a public agency's website. GovInfo
is the U.S. Government Publishing Office's own API, it is documented, it is intended for this, and
DEMO_KEY works without registration.

⚠︎ AND THE COST OF THAT CHOICE, STATED PLAINLY: GovInfo's GAOREPORTS collection is an ARCHIVE. Its
newest reports are from 2008. The licence basis is identical, the length and structure are what
this kit needs, and the subject spread is genuinely wide — but these are not current reports, and
anything the briefs say about the world is the world of 1994-2008. That is a property of the
corpus, not of the pipeline, and it is recorded here, in SOURCES.md and on the kit's Data lens
rather than left for a reader to notice.

⚑ DEMO_KEY CANNOT FILL THIS CORPUS, AND THE NUMBERS ARE WORSE THAN "rate-limited" SUGGESTS.
Measured 2026-08-05 off the 429's own headers: x-ratelimit-limit 10, x-ratelimit-remaining 0,
retry-after 67920 — a TEN-request budget refilling after about NINETEEN HOURS, not an hourly
window. A document costs three calls (search, summary, text) and the topic loop below spends one
per topic on searches alone, so a whole window buys one or two reports. Set GOVINFO_API_KEY (free,
from api.data.gov) before expecting this to fetch anything. Waiting and retrying is not a plan.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "_fetched")
SEARCH = "https://api.govinfo.gov/search"
API_KEY = os.environ.get("GOVINFO_API_KEY", "DEMO_KEY")

# ⚑ TOPICS, NOT ONE SUBJECT — and this is the same reasoning UC002 records for its conditions.
# Fifty reports about federal IT would produce fifty documents that phrase everything the same
# way, and a rubric score on that measures how well the model reads one house style. The point of
# a cross-domain kit is that a forker sees it work on subjects unlike each other.
TOPICS = [
    "information technology modernization",
    "medicare health care",
    "disaster recovery FEMA",
    "defense acquisition",
    "education student aid",
    "environmental protection cleanup",
    "veterans health administration",
    "transportation infrastructure safety",
]
PER_TOPIC = 6

# Reports only. A "T-" prefixed package is TESTIMONY — a statement to a committee, typically ten
# pages and shaped nothing like a report. Mixing them in would put two different document kinds in
# one corpus and make every length-related finding unreadable.
MIN_PAGES = 25


def _get(url, timeout=60):
    req = urllib.request.Request(
        url,
        # A contactable UA is basic manners against a public endpoint that costs someone money.
        headers={"User-Agent": "adhana-foundry-kits/docs-summarise (public-domain corpus build)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _post(url, payload, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"content-type": "application/json",
                 "User-Agent": "adhana-foundry-kits/docs-summarise (public-domain corpus build)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def search(topic, n):
    """Newest first, so the corpus sits at the recent end of whatever the archive holds."""
    body = {"query": "collection:GAOREPORTS %s" % topic,
            "pageSize": n * 3,          # over-fetch: testimony and short reports are filtered below
            "offsetMark": "*",
            "sorts": [{"field": "publishdate", "sortOrder": "DESC"}]}
    return _post("%s?api_key=%s" % (SEARCH, urllib.parse.quote(API_KEY)), body)


def summary(package_id):
    return json.loads(_get("https://api.govinfo.gov/packages/%s/summary?api_key=%s"
                           % (package_id, urllib.parse.quote(API_KEY))).decode("utf-8"))


def text(package_id):
    return _get("https://api.govinfo.gov/packages/%s/htm?api_key=%s"
                % (package_id, urllib.parse.quote(API_KEY)), timeout=90).decode("utf-8", "replace")


def main():
    os.makedirs(RAW, exist_ok=True)
    kept, seen = 0, set()
    for topic in TOPICS:
        try:
            page = search(topic, PER_TOPIC)
        except Exception as exc:
            # A failed topic is reported and skipped, never retried into a rate limit. The corpus
            # is smaller and the build says so; a fetcher that hammers a public API to fill a
            # quota is a worse thing to publish than a short corpus.
            print("  !! %-38s %s" % (topic, str(exc)[:70]))
            continue

        took = 0
        for r in page.get("results", []):
            pid = r.get("packageId", "")
            if took >= PER_TOPIC or pid in seen or "-T-" in pid:
                continue
            try:
                meta = summary(pid)
                pages = int(meta.get("pages") or 0)
            except Exception as exc:
                print("  !! %-38s %s" % (pid, str(exc)[:70]))
                continue
            if pages < MIN_PAGES:
                continue
            try:
                body = text(pid)
            except Exception as exc:
                print("  !! %-38s %s" % (pid, str(exc)[:70]))
                continue

            seen.add(pid)
            took += 1
            kept += 1
            with open(os.path.join(RAW, "%s.json" % pid), "w", encoding="utf-8") as f:
                json.dump({"packageId": pid, "title": meta.get("title"),
                           "dateIssued": meta.get("dateIssued"), "pages": pages,
                           "governmentAuthor1": meta.get("governmentAuthor1"),
                           "topic": topic, "html": body}, f, ensure_ascii=False)
            print("  %-38s %-22s %3d pages" % (topic[:38], pid, pages))
            # Deliberate, not tuned: a public API paid for by somebody else.
            time.sleep(0.5)

    print("\nfetched %d report(s) into %s" % (kept, os.path.relpath(RAW, HERE)))
    print("next: python -m tools.build_corpus")


if __name__ == "__main__":
    main()
