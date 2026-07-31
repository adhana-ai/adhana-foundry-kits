"""Turn the fetched HTML into the shipped corpus: 40 documents across FIVE formats.

WHY FIVE FORMATS, ONE PER DOCUMENT.
A real document collection is heterogeneous. Converting all forty pages into all five formats would
make a 200-file corpus that is really one corpus five times, and retrieval over it would never meet
the problem that actually bites: some of your documents are PDFs and the text does not come out
cleanly. So each page is assigned exactly one format, and the mix is weighted the way a real
folder is -- mostly clean text, a minority of binaries.

THE PDF AND DOCX SHARE ARE DELIBERATE, NOT DECORATION.
"Not extracted" is one of the four retrieval failure causes the Foundry Failure Modes page already
publishes, and it is the only one a corpus can refuse to exhibit. A corpus that cannot fail that
way makes the taxonomy a list of categories with nothing in them.

YOU DO NOT NEED TO RUN THIS -- the corpus is checked in. It is recorded here because a claim about
how a dataset was built is worth nothing if the steps are not written down. Note that it is the one
part of this kit that is NOT portable: it shells out to Chrome for PDF and to macOS `textutil` for
DOCX. That is fine for a build step whose output ships; it would not be fine anywhere in `src/`,
and it is not.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "data", "_fetched")
OUT = os.path.join(HERE, "data", "corpus")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Assigned by hand rather than by hash, so the mix is a decision someone made and can argue with.
# The two binary formats carry pages whose content is prose rather than syntax tables, because a
# railroad diagram surviving a PDF round-trip proves nothing about text extraction.
FORMAT = {
    "pdf":  ["whentouse", "isolation", "arch", "appfileformat", "security"],
    "docx": ["faq", "quirks", "howtocompile"],
    "txt":  ["lang_naming", "lang_keywords", "inmemorydb", "uri", "limits", "dbhash", "csv",
             "zipfile"],
    "md":   ["wal", "datatype3", "nulls", "autoinc", "foreignkeys", "withoutrowid", "rowidtable",
             "expridx", "queryplanner", "lockingv3", "sharedcache", "tempfiles"],
}
# Everything not named above stays as the HTML it arrived as.


def convert(html, md):
    # The runtime pipeline reads these same documents, so it must use this same parser.
    # src/extract.py owns it; a second copy here would drift and the corpus would stop matching
    # what the index was built from.
    sys.path.insert(0, HERE)
    from src.extract import HtmlText
    p = HtmlText(md)
    p.feed(html)
    return p.text()


def main():
    os.makedirs(OUT, exist_ok=True)
    assigned = {p: f for f, ps in FORMAT.items() for p in ps}
    pages = sorted(x[:-5] for x in os.listdir(SRC) if x.endswith(".html"))
    if not pages:
        print("!! nothing in data/_fetched -- run tools/fetch_corpus.py first", file=sys.stderr)
        return 1

    tally = {}
    for page in pages:
        raw = open(os.path.join(SRC, page + ".html"), encoding="utf-8", errors="replace").read()
        fmt = assigned.get(page, "html")
        dest = os.path.join(OUT, page + "." + fmt)
        if fmt == "html":
            open(dest, "w", encoding="utf-8").write(raw)
        elif fmt in ("md", "txt"):
            open(dest, "w", encoding="utf-8").write(convert(raw, fmt == "md"))
        elif fmt == "pdf":
            subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            "--print-to-pdf=" + dest, "file://" + os.path.join(SRC, page + ".html")],
                           check=True, capture_output=True)
        elif fmt == "docx":
            subprocess.run(["textutil", "-convert", "docx", "-output", dest,
                            os.path.join(SRC, page + ".html")], check=True, capture_output=True)
        tally[fmt] = tally.get(fmt, 0) + 1
        print("  %-18s -> .%s  %6.1f KB" % (page, fmt, os.path.getsize(dest) / 1024))

    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print("\ncorpus: %d documents, %.1f KB" % (len(pages), total / 1024))
    for f in ("html", "md", "txt", "pdf", "docx"):
        print("  %-5s %d" % (f, tally.get(f, 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
