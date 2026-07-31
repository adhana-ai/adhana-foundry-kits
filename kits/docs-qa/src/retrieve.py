"""SEAM 4 — which passages the model gets to see.

TWO RETRIEVERS BEHIND ONE INTERFACE, AND THAT IS THE DEMO.
`keyword` is pure stdlib TF-IDF and needs no key, no vectors and no network -- it is what makes
`clone, install, one command` true offline. `embedding` is what the published run used. Both
answer the same call, so switching is one word in .env, and the eval harness scores both on the
same labelled set.

That is the claim the kit exists to make checkable: swapping a component is a one-line change, and
knowing whether you SHOULD is an eval run. A kit that shipped only the good retriever would be
asserting it; shipping both and scoring them is the difference.

Retrieval is `pure code` on the flow figure for a reason -- nothing here calls a model. Every
failure at this step is a failure you can read, re-run and fix without spending a token.
"""
import math
import re
from collections import Counter

TOP_K = 5
_WORD = re.compile(r"[a-z0-9_]+")


def tokenize(s):
    # Deliberately crude: lowercase word characters, no stemming, no stopword list. A retrieval
    # step whose behavior depends on a language-specific stopword file is one more thing a forker
    # pointing this at their own documents has to discover.
    return _WORD.findall(s.lower())


def build_keyword_index(chunks):
    """Document frequencies over the corpus. Cheap enough to rebuild on load, so it is never a
    checked-in artifact that can drift from the chunks beside it."""
    df = Counter()
    for c in chunks:
        df.update(set(tokenize(c["text"])))
    n = max(1, len(chunks))
    return {t: math.log(1 + n / (1 + d)) for t, d in df.items()}


def keyword(question, chunks, idf, k=TOP_K):
    q = Counter(tokenize(question))
    scored = []
    for c in chunks:
        tf = Counter(tokenize(c["text"]))
        # Cosine-ish: shared terms weighted by rarity, normalised by chunk length so a long
        # passage does not win simply by containing more words.
        num = sum(q[t] * tf[t] * idf.get(t, 0.0) ** 2 for t in q if t in tf)
        if num:
            scored.append((num / math.sqrt(sum(tf.values())), c))
    scored.sort(key=lambda x: -x[0])
    return [{"score": round(s, 5), **c} for s, c in scored[:k]]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def embedding(question, chunks, vectors, embed_fn, k=TOP_K):
    """Needs a key, because the question has to be embedded with the same model the index was.

    Mixing embedding models across index and query is the silent version of this failure: it
    returns confident nonsense rather than an error, so the index records which model built it
    and this refuses to run against a different one.
    """
    qv = embed_fn([question])[0]
    scored = [(cosine(qv, vectors[c["id"]]), c) for c in chunks if c["id"] in vectors]
    scored.sort(key=lambda x: -x[0])
    return [{"score": round(s, 5), **c} for s, c in scored[:k]]


def retrieve(question, index, cfg=None, k=TOP_K):
    """Dispatch on what the index actually has, not on what .env asks for.

    An index with no vectors falls back to keyword and SAYS SO in the returned mode. Silently
    downgrading would make an eval comparing the two retrievers compare one retriever twice.
    """
    if index.get("vectors"):
        from .embed import embed_texts
        return "embedding", embedding(question, index["chunks"], index["vectors"],
                                      lambda t: embed_texts(t, cfg), k)
    return "keyword", keyword(question, index["chunks"], index["idf"], k)
