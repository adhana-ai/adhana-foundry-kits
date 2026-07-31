"""Fetch the sample corpus: 40 pages of SQLite documentation.

WHY THIS CORPUS.
It is PUBLIC DOMAIN, and unusually explicitly so. sqlite.org/copyright.html says "All of the code
and documentation in SQLite has been dedicated to the public domain by the authors" -- code AND
documentation, named. No attribution clause, no share-alike, no notice file. Shipping documents in
a public MIT repo is the one legal landmine in a kit like this, and this is the cleanest answer
available.

The obvious alternative was AI Foundry's own guide pages, which we own outright. It was rejected:
every guide sits behind the site's access gate, so publishing forty of them here would un-gate them
by the back door.

WHY THESE FORTY.
Small enough that a forker can read the whole corpus in a text editor, and deliberately overlapping
-- nulls against datatype3, rowidtable against withoutrowid, expridx against lang_analyze. A corpus
of forty unrelated pages makes retrieval look easy and teaches nothing. The failure taxonomy needs
somewhere for "bad ranking" to actually come from.

YOU DO NOT NEED TO RUN THIS. The corpus is checked in. This script records how it was built and
lets you rebuild it if sqlite.org moves on -- which will change the corpus, and therefore the
dataset version, and therefore every number the report publishes.
"""
import os
import sys
import time
import urllib.request

BASE = "https://www.sqlite.org/%s.html"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "corpus", "html")

# Verified 200 on 2026-07-31, one HEAD each. A page that 404s is a hard error below rather than a
# quietly shorter corpus -- a dataset that silently shrinks is a dataset whose version lies.
PAGES = [
    "lang_naming", "dbhash", "rowidtable", "features", "quickstart", "csv", "inmemorydb",
    "expridx", "lang_keywords", "autoinc", "lang_mathfunc", "lang_vacuum", "security", "uri",
    "sharedcache", "nulls", "isolation", "withoutrowid", "zipfile", "howtocompile", "whentouse",
    "limits", "arch", "lang_analyze", "lang_transaction", "appfileformat", "lang_datefunc",
    "backup", "lockingv3", "lang_explain", "quirks", "tempfiles", "queryplanner", "faq",
    "datatype3", "rtree", "wal", "lang_corefunc", "foreignkeys", "testing",
]


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for i, page in enumerate(PAGES):
        dest = os.path.join(OUT, page + ".html")
        url = BASE % page
        req = urllib.request.Request(url, headers={"User-Agent": "adhana-foundry-kits/docs-qa"})
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                print("!! %s returned %s" % (url, r.status), file=sys.stderr)
                return 1
            body = r.read()
        with open(dest, "wb") as f:
            f.write(body)
        total += len(body)
        print("  %2d/%d  %-18s %6.1f KB" % (i + 1, len(PAGES), page, len(body) / 1024))
        time.sleep(0.4)          # a courtesy to a project that gives its documentation away
    print("corpus: %d pages, %.1f KB" % (len(PAGES), total / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
