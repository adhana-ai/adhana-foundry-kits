"""Transcribe the rulebook from the eCFR — by code, so no rule is ever typed from memory.

    python -m tools.build_rulebook          # uses the cached XML if present, else fetches
    python -m tools.build_rulebook --fetch  # force a fresh pull

Writes data/rulebook.json. YOU DO NOT NEED TO RUN THIS — the output is checked in.

── WHY A SCRIPT AND NOT A HAND-WRITTEN JSON ───────────────────────────────────────────────────
This kit's entire claim is that it checks a real document against the real rule that binds it. A
rulebook typed from memory would quietly break that claim in the one place nobody would look — the
rules themselves — and no gate downstream can tell a misremembered requirement from a correct one,
because both are well-formed strings. So the element names, their citations and their definitions
are PARSED out of the regulation's own XML. If a rule is wrong here, it is wrong in the eCFR.

── WHERE EACH HALF OF A RULE COMES FROM ───────────────────────────────────────────────────────
The regulation splits what we need across two sections, and both are transcribed:

  §11.28(a)(2)   the binding LIST — which data elements a responsible party must submit for an
                 applicable clinical trial, as a lettered outline. This gives the element name
                 and its citation, and nothing else: the paragraph is a bare list.
  §11.10(b)      the DEFINITIONS — "Enrollment means …", "Why Study Stopped means …". This gives
                 the requirement text, verbatim, and it is the reason a rule can say something
                 more useful than "the record must contain an Enrollment field".

Matching is by element NAME, which is the same vocabulary in both sections because the part
defines its terms once and then lists them. An element with no definition in §11.10(b) keeps its
name as the requirement and records `definition: null` rather than inventing prose for it.

── THE TWO DEFINITIONS THAT MAKE `breached` A REAL STATE ──────────────────────────────────────
Most elements are present-or-absent, which yields met / never-addressed and no middle. Two
definitions carry a CONDITION inside them, and those are what let a document be *addressed and
deficient* — the state this kit exists to separate from silence:

  Why Study Stopped   "for a clinical trial that is suspended or terminated or withdrawn prior to
                      its planned completion" — so on a terminated record its absence is a BREACH,
                      and on a completed one the rule does not apply at all. Filtering a corpus to
                      COMPLETED, as UC007's fetcher does, flattens this rule to a constant. That
                      is measured, and it is why this kit does not reuse that corpus.
  Enrollment          "Once the trial has reached the primary completion date, the responsible
                      party must update the Enrollment data element to reflect the actual number"
                      — so an ESTIMATED count on a record past its primary completion date is a
                      breach, and the same count before that date is fine.

Both conditions are evaluated in `tools/build_corpus.py` against structured fields, never against
the rendered prose, so a gold label cannot drift from the document it labels.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(HERE, "data", "_fetched", "ecfr-title42-part11.xml")
OUT = os.path.join(HERE, "data", "rulebook.json")

# A PAST DATE IS REQUIRED. The versioner serves point-in-time snapshots; today's date 404s because
# the snapshot for it does not exist yet. 2025-01-01 returns 200 and is the edition transcribed.
EDITION = "2025-01-01"
SRC = ("https://www.ecfr.gov/api/versioner/v1/full/%s/title-42.xml"
       "?chapter=I&subchapter=A&part=11" % EDITION)


def fetch_xml():
    os.makedirs(os.path.dirname(XML), exist_ok=True)
    req = urllib.request.Request(
        SRC, headers={"User-Agent": "adhana-foundry-kits/docs-comply (rulebook transcription)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    with open(XML, "wb") as fh:
        fh.write(data)
    return data


def section_text(root, number):
    for div in root.iter():
        if div.get("TYPE") == "SECTION" and div.get("N") == number:
            return re.sub(r"[ \t]+", " ", "".join(div.itertext()))
    raise SystemExit("§%s not found in the XML — the regulation was restructured; "
                     "read it before changing this parser." % number)


# ── §11.28(a)(2): the lettered outline. (i)/(ii)/(iii)/(iv) are groups; (A)…(X) are elements.
GROUP_RE = re.compile(r"\((?P<rn>i|ii|iii|iv)\)\s*(?P<name>[A-Z][^:]{3,60}):")
ELEM_RE = re.compile(r"\((?P<let>[A-X])\)\s*(?P<name>.+?)(?=\s*\([A-X]\)\s|$)", re.S)

# A lettered marker inside an element's own text is a CROSS-REFERENCE, not the next element.
# Element (R) cites "§ 11.28(a)(2)(iv)(C)" and "§ 11.28(a)(2)(iii)(C)" inside its own sentence,
# and a naive scan reads both as a new element (C) — which is exactly what the first run did,
# emitting two rules whose "element" was the tail of a cross-reference. Stripping citations
# before the scan removes the bait; the monotonic-letter check below is the backstop that would
# catch any other embedded marker this pattern does not anticipate.
XREF_RE = re.compile(r"§+\s*\d+\.\d+(?:\([a-zA-Z0-9]+\))+")


def parse_elements(s28):
    """Pull the (a)(2) element list with its citations, in document order."""
    start = s28.find("(2) For such applicable clinical trials that are initiated on or after")
    end = s28.find("(b) Pediatric postmarket surveillance")
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("could not bound §11.28(a)(2) — the section was restructured.")
    seg = XREF_RE.sub("that cross-reference", s28[start:end])

    groups = [(m.start(), m.group("rn"), m.group("name").strip()) for m in GROUP_RE.finditer(seg)]
    if not groups:
        raise SystemExit("no (i)/(ii)/(iii)/(iv) groups found inside §11.28(a)(2).")

    out = []
    for gi, (gpos, rn, gname) in enumerate(groups):
        gend = groups[gi + 1][0] if gi + 1 < len(groups) else len(seg)
        body = seg[gpos:gend]
        expect = "A"
        for m in ELEM_RE.finditer(body):
            let = m.group("let")
            # THE LETTERS MUST ASCEND BY ONE. The outline is A, B, C … and anything out of
            # sequence is not an element of this list. This is a structural check rather than a
            # textual one, which is why it survives wording changes the regexes would not.
            if let != expect:
                continue
            expect = chr(ord(let) + 1)

            name = re.sub(r"\s+", " ", m.group("name")).strip()
            name = re.sub(r"^and\s+", "", name)
            name = re.sub(r";\s*and\s*$", "", name).rstrip(";. ")

            # The LAST element of a group runs to the end of the group, so an element that is
            # followed by a proviso swallows it — "(H) Availability of Expanded Access. If
            # expanded access is available … an expanded access record must be submitted".
            # Cut at the first sentence boundary and keep the proviso as the note. The lookbehind
            # protects abbreviations: the period in "U.S. FDA-regulated Device Product" follows a
            # capital and is not a sentence end, so those element names stay whole.
            parts = re.split(r"(?<![A-Z])\.\s+(?=[A-Z])", name, maxsplit=1)
            tail_note = None
            if len(parts) == 2:
                name, tail_note = parts[0].strip(), parts[1].strip()
            # Elements whose list entry carries a trailing qualifier ("Study Phase, for an
            # applicable drug clinical trial") keep the qualifier as `applies_note` rather than
            # letting it contaminate the element name the definition is matched on. The split is
            # on the FIRST comma followed by for/if/by — "Primary Disease or Condition Being
            # Studied in the Trial, or the Focus of the Study" must not be split, and is not.
            note = tail_note
            m2 = re.search(r",\s*((?:for|if|by)\b.*)$", name, re.S)
            if m2:
                note = "; ".join(x for x in (m2.group(1).strip(), tail_note) if x)
                name = name[:m2.start()].strip()
            if note:
                note = re.sub(r";\s*and\s*$", "", note).strip().rstrip(";")
            if len(name) < 3:
                continue
            out.append({
                "cite": "42 CFR §11.28(a)(2)(%s)(%s)" % (rn, let),
                "group": gname.rstrip(":").strip(),
                "element": name,
                "applies_note": note,
            })
    return out


# ── §11.10(b): "<Element> means <definition>." runs of numbered definitions.
# `means` is followed by a COMMA as often as by a space — "Why Study Stopped means, for a clinical
# trial that is suspended or terminated…". Demanding whitespace dropped that definition silently
# on the first run, and it is the one definition this kit most depends on, so the separator is
# `[,\s]` in both the match and the lookahead.
DEF_RE = re.compile(r"\(\d+\)\s*(?P<name>[A-Z][A-Za-z0-9 ,/\-\(\)\.']{2,110}?)\s+means[:,\s]\s*(?P<body>.*?)"
                    r"(?=\(\d+\)\s*[A-Z][A-Za-z0-9 ,/\-\(\)\.']{2,110}?\s+means[:,\s]|$)", re.S)


# Not every term is defined inside the numbered run. §11.10(a) defines "Responsible party",
# "Clinical trial" and others as running prose with no "(n)" marker, and the first version of this
# parser — which required the marker — left those rules with a null definition. This second
# pattern catches the unnumbered form; the numbered pass wins on any name they both define.
BARE_DEF_RE = re.compile(r"(?:^|\.\s+)(?P<name>[A-Z][A-Za-z0-9 ,/\-\(\)\.']{2,110}?)\s+means[:,\s]\s*"
                         r"(?P<body>.*?)(?=\.\s+[A-Z][A-Za-z0-9 ,/\-\(\)\.']{2,110}?\s+means[:,\s]|$)",
                         re.S)


def parse_definitions(s10):
    defs = {}
    for m in BARE_DEF_RE.finditer(s10):
        name = re.sub(r"\s+", " ", m.group("name")).strip().rstrip(",")
        name = re.sub(r"^\(\d+\)\s*", "", name)
        body = re.sub(r"\s+", " ", m.group("body")).strip()
        defs.setdefault(name.lower(), {"text": body, "cite": "42 CFR §11.10"})
    for m in DEF_RE.finditer(s10):
        name = re.sub(r"\s+", " ", m.group("name")).strip().rstrip(",")
        body = re.sub(r"\s+", " ", m.group("body")).strip()
        defs[name.lower()] = {"text": body, "cite": "42 CFR §11.10(b)"}
    return defs


def match_definition(element, defs):
    key = element.lower().strip()
    if key in defs:
        return defs[key]
    # The list and the definitions agree on vocabulary but not always on plurality or on a
    # parenthetical ("Intervention Name(s)"). Try the obvious normalisations, then give up —
    # a missed match costs a null definition, never a wrong one.
    for cand in (key.replace("(s)", ""), key.replace("(s)", "s"),
                 key.rstrip("s"), key + "s",
                 re.sub(r"\s*\([^)]*\)", "", key).strip()):
        if cand in defs:
            return defs[cand]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="force a fresh pull of the eCFR XML")
    ap.add_argument("--print-hash", action="store_true",
                    help="print the fingerprint of the rulebook on disk and exit, without "
                         "rebuilding. This is the value src/comply.py pins as RULEBOOK_SHA256.")
    a = ap.parse_args()
    if getattr(a, "print_hash", False):
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.comply import rulebook_fingerprint as _fp, RULEBOOK_SHA256 as _pinned
        with open(OUT, encoding="utf-8") as _fh:
            _rules = json.load(_fh)["rules"]
        _got = _fp(_rules)
        print(_got)
        print("pinned in src/comply.py: %s" % _pinned)
        print("MATCH" if _got == _pinned else "MISMATCH — the rulebook on disk is not the pinned one")
        return

    if a.fetch or not os.path.exists(XML):
        print("fetching %s" % SRC)
        fetch_xml()
    root = ET.parse(XML).getroot()

    s28 = section_text(root, "11.28")
    s10 = section_text(root, "11.10")
    elements = parse_elements(s28)
    defs = parse_definitions(s10)

    rules, matched = [], 0
    for i, e in enumerate(elements, 1):
        d = match_definition(e["element"], defs)
        if d:
            matched += 1
        rules.append({
            "id": "R-%02d" % i,
            "cite": e["cite"],
            "group": e["group"],
            "element": e["element"],
            "applies_note": e["applies_note"],
            "requirement": ("The responsible party must submit the data element %r."
                            % e["element"]),
            "definition": d["text"] if d else None,
            "definition_cite": d["cite"] if d else None,
        })

    payload = {
        "source": "Electronic Code of Federal Regulations (eCFR)",
        "title": "42 CFR Part 11 — Clinical Trials Registration and Results Information Submission",
        "section": "§11.28(a)(2) — clinical trial registration information",
        "definitions_section": "§11.10(b)",
        "edition": EDITION,
        "url": SRC,
        "licence": "public domain — a work of the U.S. Government (17 U.S.C. §105)",
        "transcribed_by": "tools/build_rulebook.py (parsed from the eCFR XML; never typed)",
        "rule_count": len(rules),
        "rules": rules,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
        fh.write("\n")

    # ⚑ THE NEW FINGERPRINT, PRINTED WHERE THE PERSON WHO CHANGED THE RULES IS LOOKING. A pin in
    # code that a legitimate rebuild cannot easily update is a pin somebody deletes; this makes
    # updating it a copy-paste with a diff, which is exactly the deliberate act it should be.
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.comply import rulebook_fingerprint as _fp, RULEBOOK_SHA256 as _pinned
    _got = _fp(rules)
    print("rulebook: %d rules -> data/rulebook.json" % len(rules))
    print("   fingerprint: %s" % _got)
    if _got != _pinned:
        print("   ⚠︎ THIS DOES NOT MATCH src/comply.py's RULEBOOK_SHA256 (%s...)." % _pinned[:16])
        print("      The rules changed. If that was intended, paste the value above into")
        print("      src/comply.py; every run will refuse to start until you do. If it was NOT")
        print("      intended, find out what changed before running anything.")
    print("   definitions matched from §11.10(b): %d/%d" % (matched, len(rules)))
    by_group = {}
    for r in rules:
        by_group[r["group"]] = by_group.get(r["group"], 0) + 1
    for g in by_group:
        print("   %-28s %d" % (g, by_group[g]))


if __name__ == "__main__":
    main()
