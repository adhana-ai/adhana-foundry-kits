# Where this corpus came from, and why we may ship it

**40 documents. Public domain. Fetched 2026-07-31 from `https://www.sqlite.org/`.**

This file sits next to the documents on purpose. How the corpus was built is recorded in
`tools/fetch_corpus.py` and `tools/build_corpus.py` — but both of those scripts open by telling you
that **you do not need to run them**, so neither is a place a licence can live. A claim about the
right to redistribute forty files has to travel with the files.

## The licence

SQLite's documentation is dedicated to the public domain, and unusually explicitly — the dedication
names documentation and not only code. From <https://www.sqlite.org/copyright.html>, under the
heading *"SQLite Is Public Domain"*:

> All of the code and documentation in SQLite has been dedicated to the public domain by the
> authors.

Verified against that page on 2026-07-31. No attribution clause, no share-alike, no notice file, no
licence to propagate. That is why this corpus and not another: shipping somebody else's documents
inside a public MIT repository is the one genuine legal hazard in a kit like this, and this is the
cleanest answer available.

**The obvious alternative was rejected.** AI Foundry's own guide pages are ours outright — but every
guide sits behind the site's access gate, so publishing forty of them here would have un-gated them
by the back door.

## What we changed, and what that means for provenance

**Every document was fetched as HTML.** The five formats below are *ours*: `tools/build_corpus.py`
converted each page into exactly one target format. **sqlite.org does not publish DOCX or PDF
versions of these pages** — if you want the originals, follow the source link, which is always the
`.html` page.

The conversion is why the corpus is heterogeneous, and the heterogeneity is the point. `not_extracted`
is one of the four retrieval failure causes this kit reports, and it is the only one a corpus can
refuse to exhibit: a folder of clean Markdown cannot show text failing to come out of a PDF.

| format | count | how it was produced |
|---|---|---|
| html | 12 | the fetched page, cleaned |
| md | 12 | converted from the fetched HTML |
| txt | 8 | converted from the fetched HTML |
| pdf | 5 | rendered from the fetched HTML via headless Chrome |
| docx | 3 | converted from the fetched HTML via macOS `textutil` |

## The 40 documents

Every source is `https://www.sqlite.org/<name>.html`, where `<name>` is the document id below.

| document | shipped as | source |
|---|---|---|
| appfileformat | pdf | <https://www.sqlite.org/appfileformat.html> |
| arch | pdf | <https://www.sqlite.org/arch.html> |
| autoinc | md | <https://www.sqlite.org/autoinc.html> |
| backup | html | <https://www.sqlite.org/backup.html> |
| csv | txt | <https://www.sqlite.org/csv.html> |
| datatype3 | md | <https://www.sqlite.org/datatype3.html> |
| dbhash | txt | <https://www.sqlite.org/dbhash.html> |
| expridx | md | <https://www.sqlite.org/expridx.html> |
| faq | docx | <https://www.sqlite.org/faq.html> |
| features | html | <https://www.sqlite.org/features.html> |
| foreignkeys | md | <https://www.sqlite.org/foreignkeys.html> |
| howtocompile | docx | <https://www.sqlite.org/howtocompile.html> |
| inmemorydb | txt | <https://www.sqlite.org/inmemorydb.html> |
| isolation | pdf | <https://www.sqlite.org/isolation.html> |
| lang_analyze | html | <https://www.sqlite.org/lang_analyze.html> |
| lang_corefunc | html | <https://www.sqlite.org/lang_corefunc.html> |
| lang_datefunc | html | <https://www.sqlite.org/lang_datefunc.html> |
| lang_explain | html | <https://www.sqlite.org/lang_explain.html> |
| lang_keywords | txt | <https://www.sqlite.org/lang_keywords.html> |
| lang_mathfunc | html | <https://www.sqlite.org/lang_mathfunc.html> |
| lang_naming | txt | <https://www.sqlite.org/lang_naming.html> |
| lang_transaction | html | <https://www.sqlite.org/lang_transaction.html> |
| lang_vacuum | html | <https://www.sqlite.org/lang_vacuum.html> |
| limits | txt | <https://www.sqlite.org/limits.html> |
| lockingv3 | md | <https://www.sqlite.org/lockingv3.html> |
| nulls | md | <https://www.sqlite.org/nulls.html> |
| queryplanner | md | <https://www.sqlite.org/queryplanner.html> |
| quickstart | html | <https://www.sqlite.org/quickstart.html> |
| quirks | docx | <https://www.sqlite.org/quirks.html> |
| rowidtable | md | <https://www.sqlite.org/rowidtable.html> |
| rtree | html | <https://www.sqlite.org/rtree.html> |
| security | pdf | <https://www.sqlite.org/security.html> |
| sharedcache | md | <https://www.sqlite.org/sharedcache.html> |
| tempfiles | md | <https://www.sqlite.org/tempfiles.html> |
| testing | html | <https://www.sqlite.org/testing.html> |
| uri | txt | <https://www.sqlite.org/uri.html> |
| wal | md | <https://www.sqlite.org/wal.html> |
| whentouse | pdf | <https://www.sqlite.org/whentouse.html> |
| withoutrowid | md | <https://www.sqlite.org/withoutrowid.html> |
| zipfile | txt | <https://www.sqlite.org/zipfile.html> |

## Why these forty

Small enough that you can read the entire corpus in a text editor, and **deliberately overlapping**:
`nulls` against `datatype3`, `rowidtable` against `withoutrowid`, `expridx` against `lang_analyze`.
Forty unrelated pages would make retrieval look easy and teach nothing — the failure taxonomy needs
somewhere for `bad_ranking` to genuinely come from, and near-duplicate subject matter is where it
comes from.

## If you re-fetch

`tools/fetch_corpus.py` will rebuild it, and **the result will not be identical** — sqlite.org
revises its documentation. A changed corpus is a changed dataset version, which invalidates every
number in `results/` and every row in `data/labelled.jsonl`. Re-label before believing a score.

## No thanks are owed, but they are offered

The SQLite project gives its documentation away with no strings. This kit's fetch script sleeps
between requests for that reason. If you re-run it, leave that in.
