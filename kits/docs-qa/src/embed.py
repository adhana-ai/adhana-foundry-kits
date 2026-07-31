"""Embeddings for the vector retriever. Needs a key; the keyword retriever does not.

AN HONEST CONSTRAINT, RECORDED RATHER THAN PAPERED OVER.
The completion adapter is provider-neutral by design, but embeddings are not symmetric across
vendors: several providers that serve chat models serve no embedding endpoint at all. So this
speaks the OpenAI-compatible `/embeddings` shape, which OpenAI, Together, Mistral, Voyage and
local servers all implement -- and a forker whose completion provider has no embeddings endpoint
points EMBED_BASE_URL at one that does, or stays on the keyword retriever, which costs nothing and
still answers.

That asymmetry is the honest version of "swapping models is one line": it is one line for
completions, and one line plus a re-index for embeddings, because the index is derived from the
model that built it.
"""
import json
import os

from .adapters import AdapterError, _post

BATCH = 64


def embed_texts(texts, cfg):
    base = (cfg.get("embed_base_url") or cfg.get("base_url") or "").rstrip("/")
    model = cfg.get("embed_model")
    if not model:
        raise AdapterError("no EMBED_MODEL set -- the keyword retriever needs neither, and is "
                           "what runs when there are no vectors.")
    out = []
    for i in range(0, len(texts), BATCH):
        body = _post(base + "/embeddings", {"authorization": "Bearer " + cfg["api_key"]},
                     {"model": model, "input": texts[i:i + BATCH]})
        # Sort by index rather than trusting order: the spec says the response carries one, and a
        # provider that returns them out of order would silently mis-pair every vector.
        out += [d["embedding"] for d in sorted(body["data"], key=lambda d: d["index"])]
    return out


def build_vectors(index, cfg, out_path=None):
    """Embed every chunk and write vectors.json beside chunks.json.

    Records which model produced them. An index queried with a different embedding model than
    built it returns confident nonsense instead of an error, so the model id travels with the
    vectors and retrieve.py refuses the mismatch.
    """
    from .index import VECTORS
    texts = [c["text"] for c in index["chunks"]]
    vecs = embed_texts(texts, cfg)
    payload = {"model": cfg["embed_model"],
               "dimensions": len(vecs[0]) if vecs else 0,
               "vectors": {c["id"]: v for c, v in zip(index["chunks"], vecs)}}
    path = out_path or VECTORS
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return payload
