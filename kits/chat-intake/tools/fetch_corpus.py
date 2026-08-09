#!/usr/bin/env python3
"""Fetch the Schema-Guided Dialogue files this kit needs, straight from the dataset's own repo.

    python3 -m tools.fetch_corpus

⚠︎ THE DATA IS FETCHED AND NEVER VENDORED, AND ON THIS KIT THAT IS A LICENCE BOUNDARY RATHER THAN A
TIDINESS PREFERENCE. Every other kit in this repo uses US federal public-domain material or text we
wrote ourselves. SGD is **CC BY-SA 4.0** — a share-alike licence. This repo is MIT. A fetcher that
pulls the data at run time and never redistributes it is not a CC BY-SA derivative; a repo that
commits a copy of the JSON is, and that copy would have to carry CC BY-SA rather than MIT. So
`data/_fetched/` is gitignored, and it stays gitignored.

Licence, read at the source on 2026-08-09 and not from memory:
  https://raw.githubusercontent.com/google-research-datasets/dstc8-schema-guided-dialogue/master/LICENSE.txt
  opens "Attribution-ShareAlike 4.0 International". Note the filename — a fetch for `LICENSE`
  without the extension 404s, which is how a licence check comes back "no licence found" on a
  repo that has one.

⚑ IT PULLS NINE FILES, NOT ONE HUNDRED AND TWENTY-SEVEN. Banks_1 appears in 9 of the 127 train
shards. Cloning the repo is ~590 MB checked out; these nine are single-digit MB. The shard list is
DISCOVERED, not hard-coded — see `_shards()` — because a hand-listed set of source files is the
exact shape that made `figorphans` miss 205 producers over in the site repo.
"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "_fetched")
RAW = ("https://raw.githubusercontent.com/google-research-datasets/"
       "dstc8-schema-guided-dialogue/master")
SERVICE = "Banks_1"
SPLIT = "train"
# 127 shards in train. We probe them all for the service and download only the hits; the probe is
# a ranged GET of the first bytes, so a miss costs almost nothing.
SHARD_COUNT = 127


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "adhana-foundry-kits/chat-intake"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _shards():
    """Which train shards actually contain Banks_1.

    ⚠︎ DISCOVERED RATHER THAN LISTED. A shard list written down here would be correct on the day it
    was written and silently wrong the first time upstream repacked the files — and "silently" is
    the operative word, because a missing shard just means fewer dialogues, which looks like a
    smaller corpus rather than like a bug. Each dialogue object names its services, so the probe is
    a plain substring test on the downloaded shard.
    """
    hits = []
    for n in range(1, SHARD_COUNT + 1):
        name = "dialogues_%03d.json" % n
        url = "%s/%s/%s" % (RAW, SPLIT, name)
        try:
            blob = _get(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                break                       # ran off the end of the split; not an error
            raise
        if b'"%s"' % SERVICE.encode() in blob:
            hits.append((name, blob))
            print("  %-22s %8d B  <- %s" % (name, len(blob), SERVICE))
        else:
            print("  %-22s %8d B" % (name, len(blob)))
    return hits


def main():
    os.makedirs(OUT, exist_ok=True)

    print("schema (%s) ..." % SPLIT)
    schema = _get("%s/%s/schema.json" % (RAW, SPLIT))
    open(os.path.join(OUT, "schema.json"), "wb").write(schema)
    services = [s["service_name"] for s in json.loads(schema)]
    if SERVICE not in services:
        print("ERROR: %s is not in %s/schema.json — upstream changed" % (SERVICE, SPLIT),
              file=sys.stderr)
        return 1
    print("  %d service(s), %s present" % (len(services), SERVICE))

    print("licence ...")
    lic = _get("%s/LICENSE.txt" % RAW)
    open(os.path.join(OUT, "LICENSE.txt"), "wb").write(lic)
    head = lic.decode("utf-8", "replace").strip().splitlines()[0]
    print("  LICENSE.txt: %s" % head)
    if "ShareAlike" not in head:
        print("ERROR: the licence header is not the CC BY-SA one this kit was cleared against.\n"
              "       Read it before going further — the whole fetch-never-vendor design in this\n"
              "       file is downstream of that licence being share-alike.", file=sys.stderr)
        return 1

    print("shards ...")
    hits = _shards()
    if not hits:
        print("ERROR: no train shard contains %s" % SERVICE, file=sys.stderr)
        return 1
    for name, blob in hits:
        open(os.path.join(OUT, name), "wb").write(blob)

    print("\nfetched %d shard(s) carrying %s -> data/_fetched/ (gitignored, CC BY-SA 4.0)"
          % (len(hits), SERVICE))
    print("next: python3 -m tools.build_corpus")
    return 0


if __name__ == "__main__":
    sys.exit(main())
