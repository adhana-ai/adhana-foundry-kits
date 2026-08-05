"""Turn data/_fetched/*.json into the shippable corpus. No network — reproducible byte-for-byte.

Two things happen here and only one of them is formatting.

⚑ 1. THE ABSTRACT IS STRIPPED, AND IT IS THE MOST IMPORTANT LINE IN THIS FILE.
Every GAO report opens with GAO's own abstract — "Pursuant to a congressional request, GAO
reviewed …  GAO noted that: (1) … (2) …". That is ALREADY A BRIEF, written by a person, covering
what the document is about, what was found and what was recommended. Feed the document in whole
and a model can copy it, and this kit would be measuring extraction while claiming to measure
summarisation. The whole result would be an artifact of the corpus.

So the abstract is removed from the corpus document and written to data/reference/ instead, where
it is a CALIBRATION AID for a human grader — never gold. It is the source's own shape, not this
rubric's: it answers different questions in a different order, and scoring against it would be
scoring the model on how well it imitates GAO's house style.

⚠︎ AND THE STRIP IS RECORDED PER DOCUMENT, NOT ASSUMED. `stripped_chars` goes in the manifest for
every document. A silent strip that quietly matched nothing would leave the abstract in the corpus
and nothing would say so — the run would look clean and the finding would be worthless.

2. HEADINGS ARE NORMALISED so `src/segment.py` can cut on them. GAO's text rendition underlines a
heading with a rule line that carries an outline tag on the end
(`------------------------------ Letter :2.1`), and headings are indented and sometimes wrap over
two lines. The corpus is written in the plain `Heading` / `-------` form, which is the same shape
docs-extract's corpus uses — one house format across kits, so `segment.py` stays a corpus-agnostic
twenty lines instead of growing a parser per source.
"""
import html as _html
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "_fetched")
OUT = os.path.join(HERE, "data", "corpus")
REF = os.path.join(HERE, "data", "reference")
MANIFEST = os.path.join(HERE, "data", "corpus", "manifest.json")

_PRE = re.compile(r"<pre>(.*?)</pre>", re.S | re.I)
# The ASCII-representation banner GAO's text rendition puts between the abstract and the report.
_BANNER = re.compile(r"^\*{20,}\s*$.*?^\*{20,}\s*$", re.S | re.M)
# A rule line: dashes or equals, optionally followed by an outline tag such as "Letter :2.1".
_RULE = re.compile(r"^(?P<rule>[=-]{10,})(?P<tag>\s+\S.*)?$")

# ⚑ THE SECOND HIGHLIGHTS, AND THE FIRST BUILD FOUND IT — 2026-08-04.
#
# GAO's reports come in TWO text layouts and they carry their human-written brief in two different
# places. The older rendition puts an abstract above an ASCII banner, which `split_abstract`
# removes. The 2000s "accessible text" rendition has no banner at all: it embeds a `GAO Highlights:`
# block — "Why GAO Did This Study / What GAO Found / What GAO Recommends" — INSIDE the document,
# between the cover and the table of contents.
#
# ⚠︎ THE FIRST DOCUMENT THIS KIT EVER BUILT WAS THE SECOND KIND, and the abstract strip reported
# success on it: 2,767 characters removed, manifest clean, nothing to see. The Highlights block was
# still sitting at line 43 of the shipped corpus — a person's brief, answering three of this
# rubric's six sections, handed to the model as part of the document. Every score in that run would
# have been an artifact of the corpus, and the manifest would have said the strip was done.
#
# So the strip is TWO strips, each recorded separately, and `build_one` refuses a document where
# NEITHER matched. A guard that reports success because one of two conditions held is not a guard.
_HIGHLIGHTS = re.compile(r"^GAO Highlights:\s*$.*?^(?=Contents:\s*$)", re.S | re.M)
# Some renditions run Highlights straight into the letter with no Contents page. The end-of-section
# marker is GAO's own and is the safer second boundary — never a fixed line count, which would cut
# real report text out of a document that formats slightly differently.
_HIGHLIGHTS_ALT = re.compile(r"^GAO Highlights:\s*$.*?^\[End of section\]\s*$", re.S | re.M)


def _pre_text(page):
    m = _PRE.search(page)
    body = m.group(1) if m else page
    return _html.unescape(body)


def split_abstract(text):
    """(abstract, report). The banner is the divider; both halves are returned so the caller can
    record what was removed rather than discovering later that nothing was.

    A document with no banner returns ("", text) — the abstract is NOT guessed at by taking the
    first N lines. A wrong guess would delete real report text from the corpus, which is the one
    error here that cannot be seen downstream: the brief would simply be written from a document
    missing its opening, and score badly for a reason nothing recorded.
    """
    m = _BANNER.search(text)
    if not m:
        return "", text
    return text[:m.start()].strip(), text[m.end():].lstrip("\n")


def split_highlights(text):
    """(highlights, report) for the accessible-text layout. Returns ("", text) when there is no
    Highlights block, which is the correct answer for the older rendition — its brief was already
    taken by split_abstract."""
    for pat in (_HIGHLIGHTS, _HIGHLIGHTS_ALT):
        m = pat.search(text)
        if m:
            return m.group(0).strip(), text[:m.start()] + text[m.end():]
    return "", text


# Headings in the accessible-text layout are a short capitalised line ending in a colon. The bound
# is deliberately tight: a sentence ending in a colon is usually long, and a heading is usually
# short, so 70 characters separates them without needing to understand either.
_COLON_HEAD = re.compile(r"^(?P<h>[A-Z][^\n:]{2,70}):[ \t]*$", re.M)


def normalise_colon_headings(text):
    """`Background:` -> `Background` over a rule, so segment.py cuts on it like any other corpus.

    ⚠︎ ONLY WHEN THERE ARE ENOUGH OF THEM TO BE A LAYOUT. A document with three colon-lines is a
    document with three sentences that happen to end in colons, and rewriting those would invent
    sections the report does not have — section names are shown to a reader and printed in the run
    record, so an invented one is a small fabrication in an artifact whose whole job is evidence.
    """
    if len(_COLON_HEAD.findall(text)) < 8:
        return text
    return _COLON_HEAD.sub(lambda m: "%s\n%s" % (m.group("h").strip(),
                                                 "-" * max(3, min(len(m.group("h").strip()), 80))),
                           text)


def normalise_headings(text):
    """GAO's tagged rule lines -> the plain `Heading` / `-----` form segment.py cuts on."""
    lines = text.splitlines()
    out = []
    for line in lines:
        m = _RULE.match(line.rstrip())
        if not m:
            out.append(line)
            continue
        # Collect the contiguous non-blank lines already emitted: that is the heading, possibly
        # wrapped over two. Anything longer than three lines is not a heading — leave the rule
        # line alone rather than swallowing a paragraph into a title.
        head = []
        while out and out[-1].strip() and len(head) < 3:
            head.insert(0, out.pop().strip())
        if not head:
            # A rule with nothing above it is a table divider or a horizontal break, not a
            # heading. Dropped: segment.py would otherwise cut a table in half.
            continue
        title = " ".join(head)
        title = re.sub(r"\s+", " ", title).strip()
        # Title case an ALL-CAPS heading; leave a mixed-case one exactly as written. GAO shouts
        # its headings and the section name is shown to a reader and printed in the run record.
        if title.isupper():
            title = title.title()
        out.append(title)
        out.append("-" * max(3, min(len(title), 80)))
    return "\n".join(out)


def build_one(rec):
    text = _pre_text(rec["html"])
    abstract, report = split_abstract(text)
    highlights, report = split_highlights(report)
    body = normalise_headings(normalise_colon_headings(report)).strip()
    # `topic` is the SEARCH QUERY that surfaced this report, not a classification of it — the first
    # document built came back under "information technology modernization" and is about rural
    # economic development. Labelling it as a topic would put a wrong fact at the top of every
    # document in the corpus, which is a strange thing to hand a summariser.
    header = ("%s\n%s\n\nGAO report %s  ·  issued %s  ·  %s pages  ·  found via: %s\n"
              % (rec["title"], "=" * min(len(rec["title"]), 80),
                 rec["packageId"].replace("GAOREPORTS-", ""),
                 rec.get("dateIssued", ""), rec.get("pages", ""), rec.get("topic", "")))
    return header + "\n" + body + "\n", abstract, highlights


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(REF, exist_ok=True)
    manifest, skipped = [], []
    for fn in sorted(os.listdir(RAW)) if os.path.isdir(RAW) else []:
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(RAW, fn), encoding="utf-8"))
        doc, abstract, highlights = build_one(rec)
        did = rec["packageId"].replace("GAOREPORTS-", "")

        # ⚠︎ A DOCUMENT THAT SURRENDERED NEITHER BRIEF IS NOT SHIPPED. Every GAO report carries a
        # human-written brief in one of the two layouts; a document where neither pattern matched
        # is one this builder does not understand, and shipping it would put a person's summary
        # inside the thing the model is asked to summarise. It is the one defect that would
        # invalidate the whole measurement while every page looked perfect, so it fails loudly.
        if not abstract and not highlights:
            skipped.append((did, "neither an abstract banner nor a GAO Highlights block was found "
                                 "— cannot prove the document's own brief was removed"))
            continue

        with open(os.path.join(OUT, "%s.txt" % did), "w", encoding="utf-8") as f:
            f.write(doc)
        # Both go to reference/ when both exist. They answer different questions (the abstract is
        # GovInfo-era, the Highlights block is the printed report's own front page) and a grader
        # calibrating against them should see what the source actually published.
        with open(os.path.join(REF, "%s.txt" % did), "w", encoding="utf-8") as f:
            f.write("\n\n".join(x for x in (abstract, highlights) if x) + "\n")
        manifest.append({
            "id": did,
            "title": rec["title"],
            "date_issued": rec.get("dateIssued"),
            "pages": rec.get("pages"),
            "found_via": rec.get("topic"),
            "chars": len(doc),
            # The proof each strip happened, per document, in the artifact rather than in a claim.
            "abstract_chars_removed": len(abstract),
            "highlights_chars_removed": len(highlights),
        })

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"source": "api.govinfo.gov — collection GAOREPORTS",
                   "licence": "Public domain. U.S. Government works, 17 U.S.C. §105.",
                   "abstract_stripped": True,
                   "documents": manifest}, f, indent=1, ensure_ascii=False)

    total = sum(m["chars"] for m in manifest)
    print("built %d document(s), %s chars, mean %s chars"
          % (len(manifest), format(total, ","),
             format(total // max(1, len(manifest)), ",")))
    print("the document's own brief removed from %d of %d: %s chars of abstract, %s chars of "
          "GAO Highlights — written to data/reference/ as grader calibration, never as gold"
          % (sum(1 for m in manifest
                 if m["abstract_chars_removed"] or m["highlights_chars_removed"]),
             len(manifest),
             format(sum(m["abstract_chars_removed"] for m in manifest), ","),
             format(sum(m["highlights_chars_removed"] for m in manifest), ",")))
    for did, why in skipped:
        print("  SKIPPED %-18s %s" % (did, why))


if __name__ == "__main__":
    main()
