# Where this corpus came from, and what was removed from it

**Source.** U.S. Government Accountability Office reports, pulled through
`api.govinfo.gov` — the U.S. Government Publishing Office's own API — from the
`GAOREPORTS` collection. `tools/fetch_corpus.py` fetches; `tools/build_corpus.py`
turns a fetch into the files in this directory. `manifest.json` lists every
document with its GAO number, date, page count and the search that surfaced it.

**Licence.** Public domain. GAO reports are U.S. Government works and are not
subject to copyright protection in the United States (17 U.S.C. §105). The
reports say so themselves — every text rendition carries the line *"This is a
work of the U.S. government and is not subject to copyright protection in the
United States. It may be reproduced and distributed in its entirety without
further permission from GAO."* No attribution clause, no share-alike, no notice
file. GAO asks that its work not be represented as anything other than GAO's,
which this kit does not do: every document keeps its title, number and date.

## ⚠︎ Two things were REMOVED from every document, and the reason is the whole measurement

Every GAO report ships with a **human-written brief of itself**. If it is left in,
this kit measures a model's ability to *copy a summary that was already there*
while claiming to measure summarisation, and every score becomes an artifact of
the corpus rather than a fact about the model.

GAO puts that brief in two different places depending on the rendition, and both
are stripped:

| what | where it lives | typical size |
|---|---|---|
| the **abstract** | above an ASCII banner, in the older text rendition | ~2,800 chars |
| the **`GAO Highlights:` block** | inside the document, between the cover and the contents, in the 2000s "accessible text" rendition — *Why GAO Did This Study / What GAO Found / What GAO Recommends* | ~4,300 chars |

**Both strips are recorded per document** in `manifest.json` as
`abstract_chars_removed` and `highlights_chars_removed`. A document where
**neither** matched is **not shipped** — `build_corpus.py` skips it and says why.
A strip that silently matched nothing would leave a person's brief inside the
document while the manifest reported success, and nothing downstream could tell.

> The second strip was found by **building the corpus and reading the output**,
> not by planning. The first document this kit ever built reported a clean
> abstract strip — 2,767 characters removed — and still had a `GAO Highlights:`
> block sitting at line 43. A guard that reports success because one of two
> conditions held is not a guard.

**The removed text is kept**, in `data/reference/`, as **calibration for a human
grader** — never as gold. It answers different questions in a different order
from this kit's rubric, so scoring against it would score the model on how
closely it imitates GAO's house style. `evals/grade.py` mentions it and tells the
grader not to read it first.

## ⚠︎ These are archived reports, not current ones

GovInfo's `GAOREPORTS` collection ends around **2008**. The licence basis, the
length and the structure are exactly what this kit needs, and the subject spread
is genuinely wide — but anything the briefs say about the world is the world of
1994–2008.

**Why not gao.gov itself:** it answers **403** to automated requests. The product
page, the asset PDF and the site's own search endpoint all refused under a plain,
honestly-identified User-Agent. Getting past that would mean impersonating a
browser against a public agency's website, which is not a thing a public kit
should teach anyone to do. Measured 2026-08-04, not assumed.

## Rebuilding it

```bash
python -m tools.fetch_corpus      # network. Set GOVINFO_API_KEY for a real rate limit
python -m tools.build_corpus      # no network, reproducible byte-for-byte
```

`DEMO_KEY` works without registration and is limited to roughly 30 requests an
hour, which is not enough to fill a corpus — get a free key at api.data.gov.
`data/_fetched/` holds the raw pulls and is **never** shipped; `.gitignore` holds it.
