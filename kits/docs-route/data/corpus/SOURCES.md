# Where this corpus came from, and why it can be here

**Source.** The Office of the Federal Register's own public API,
`https://www.federalregister.gov/api/v1/documents.json`. Fetched by `tools/fetch_corpus.py`,
built by `tools/build_corpus.py`. `manifest.json` beside this file lists every document with its
FR document number, publication date, issuing agencies and the URL it came from.

**Licence.** Public domain. Federal Register documents are edicts of government and works of the
United States Government, and are not subject to copyright protection in the United States
(17 U.S.C. §105). The Office of the Federal Register places no restriction on reuse of the
documents themselves or of the API's output; its developer terms ask only for a courteous request
rate and that the data not be misrepresented as official. Verified against
`federalregister.gov/developers/documentation/api/v1` on 2026-08-06.

This kit fetches three requests in total, one per document type, with a one-second pause and an
identifying User-Agent. Every record carries its source URL, publication date and document number,
so nothing here is presented as anything other than the Federal Register's own.

**What was fetched and what is shipped.** `data/_fetched/` holds the raw API payloads and is
gitignored — it is the provider's response, not a corpus. What ships is one `.txt` per document
containing **only** the title, the publisher's one-line `action` and the abstract.

**What was deliberately removed, and why.**

- **The agency is not in the document text.** It is in the manifest, not in what the router reads.
  An agency name is a strong prior about the kind of thing that agency usually publishes, and a
  router that learned those priors would score well here and fail on the one document that
  matters — the unusual one from a familiar agency.
- **The `type` is not in the document text.** It is the gold label, and it lives in
  `data/gold.jsonl`, which nothing but `evals/score.py` opens. Keeping both in one file would put
  every later stage one careless read away from the answer it is being scored on.
- **Presidential Documents are not included.** 20 of 20 sampled carry no abstract, where Rules,
  Proposed Rules and Notices carry one 20 of 20, 20 of 20 and 17 of 20. Including them would have
  meant one class whose input is a bare title against three whose input is a paragraph.

**What was kept even though it makes the task easier.** The publisher's `action` line — "Final
rule.", "Notice of meeting." — often contains the answer nearly verbatim. It is genuinely present
on the real input, so removing it would build an easier problem than the one a router faces. It is
not removed; it is **measured**. The keyword baseline scores exactly this text, so the share of the
task that is "read the label off the page" is published as a number rather than argued about.

**Balance.** 40 documents per class, 120 in total, capped deterministically by document number in
`tools/build_corpus.py`. The natural distribution is nothing like this — a 150-document
newest-first sample ran 103 notices, 34 rules, 13 proposed rules — so a corpus drawn that way
would make "answer Notice every time" score 69%. The balance makes the model comparison clean and
makes the production rates unrepresentative. Both facts are stated on the kit's Corpus page.
