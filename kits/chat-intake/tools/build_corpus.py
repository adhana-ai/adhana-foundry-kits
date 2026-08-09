#!/usr/bin/env python3
"""Turn the fetched SGD shards into this kit's checklist and its labelled cases.

    python3 -m tools.build_corpus

Two outputs, and they are on opposite sides of a licence line:

  data/slots.json   SHIPS. The intents and the slot NAMES each one requires, plus the state
                    vocabulary this kit judges against. Read by the prompt, the scorer, the
                    baseline and the site's app panel — one source, exactly the discipline
                    docs-route's taxonomy.py sets out.
  data/gold.jsonl   GITIGNORED. It quotes utterances, so it is a derivative of a CC BY-SA 4.0
                    dataset and cannot sit in an MIT repo. Build it locally; it takes seconds.

⚠︎ THIS KIT IS THE FIRST WHOSE CORPUS DOES NOT SHIP, AND THAT IS A REAL COST, NOT A DETAIL. Every
other kit here renders its panel and its recorded results on a fresh clone with no key and no
network, because its corpus is public domain and committed. Here a forker must run the fetcher
first. The alternative was relicensing the repo or inventing conversations, and inventing them is
the one thing that would have destroyed the eval: the whole reason for this corpus is that the
required-fact list is published by somebody else, so "did it collect enough" is `==` against
ground truth we did not write.

⚑ WHY THE CHECKLIST IS DERIVED AND NEVER TYPED. `slots.json` is parsed out of the dataset's own
`schema.json`, the same way docs-comply's rulebook is parsed out of the eCFR XML rather than
transcribed. A hand-typed checklist would be our opinion of what a bank transfer needs, and the
kit would then grade a model against our opinion while claiming to grade it against reality.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHED = os.path.join(HERE, "data", "_fetched")
DATA = os.path.join(HERE, "data")
SERVICE = "Banks_1"

# ⚑ THE STATE VOCABULARY IS OURS AND THE CHECKLIST IS NOT, WHICH IS WHY THEY LIVE IN ONE FILE WITH
# DIFFERENT PROVENANCE. `intents` below is derived from schema.json. This is authored — it is the
# judgement the kit makes about what each outcome costs, and no dataset can supply that.
STATES = [
    {"key": "collected",
     "means": "A required fact is recorded as filled, together with the turn it was heard in.",
     "costs": "A false collected is silent for the rest of the conversation. The fact is closed, "
              "so nothing will ask for it again and nothing downstream will know it was guessed."},
    {"key": "still missing",
     "means": "Named explicitly on every turn. Never a blank cell and never a zero.",
     "costs": "Asking again for something already given, which is the most common reason a person "
              "abandons an intake flow part-way through."},
    {"key": "wrong against gold",
     "means": "A value was captured and the dialogue state says it is not that value.",
     "costs": "The most, because the checklist reads as full. A mis-recorded recipient moves money "
              "to a name nobody confirmed."},
    {"key": "the turn decision",
     "means": "Not a fact state - the kit's actual output: ask again, or stop.",
     "costs": "Stopping early hands a downstream process a record it believes is complete. Never "
              "stopping is cheaper and visible, which is exactly why the expensive failure is the "
              "one that needs its own number."},
]

# A reader's word for each intent. The keys are the dataset's; these are not, and they are the only
# strings here anybody chose.
LABELS = {"CheckBalance": "Check a balance", "TransferMoney": "Transfer money"}

HELD_OUT_SHARE = 0.20


def _held_out(dialogue_id):
    """Deterministic 20% held-out, keyed on the dialogue id.

    ⚠︎ THE SPLIT IS CARVED OUT OF `train` BECAUSE THERE IS NO ALTERNATIVE, AND THAT IS WORTH
    STATING RATHER THAN HIDING. SGD ships train/dev/test, so the obvious move is to grade on test —
    but `test` CONTAINS NO BANKS SERVICE AT ALL, and `dev` carries Banks_2, which is the same two
    intents under renamed slots (`transfer_amount`, `recipient_name`, plus a `transfer_time` that
    does not exist here). Measured at the source on 2026-08-09, not assumed from the directory
    listing.

    So: held-out is carved from train by hash, which is a weaker guarantee than a publisher's own
    split and is described as exactly that wherever the kit reports a number. Banks_2 is then a
    genuine UNSEEN-SCHEMA probe rather than a second training set, which is more than the native
    split would have given us — see docs/CORPUS.md.

    Hashed rather than shuffled so the split is identical on every machine and every re-run,
    without a seed to remember or a split file to keep in step.
    """
    h = hashlib.sha256(dialogue_id.encode("utf-8")).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF) < HELD_OUT_SHARE


def _schema():
    p = os.path.join(FETCHED, "schema.json")
    if not os.path.exists(p):
        print("ERROR: %s is missing. Run: python3 -m tools.fetch_corpus" % p, file=sys.stderr)
        return None
    for svc in json.load(open(p, encoding="utf-8")):
        if svc["service_name"] == SERVICE:
            return svc
    print("ERROR: %s is not in the fetched schema" % SERVICE, file=sys.stderr)
    return None


def _write_slots(svc):
    # ⚑ CATEGORICAL SLOTS CARRY THEIR VALUE SPACE, AND r001 IS WHY. The first real run scored 18 of
    # 28 stated facts WRONG while getting 95% of decisions right, which is not a shape a model
    # failure makes. The model had answered "savings account" where gold says "savings" — because
    # the prompt told it to copy the customer's own words, and the customer says "savings account".
    #
    # ⚠︎ THE FIX IS THE PROMPT, NOT THE SCORER. Accepting substrings would have made the numbers
    # look fine and destroyed the one thing this kit measures: "Peter" must not pass for
    # "Peter Kim". The dataset already declares which slots are closed vocabularies and what the
    # values are, so the value space is read from the schema like everything else here — never
    # typed, and never guessed at by the model.
    vals = {s["name"]: list(s.get("possible_values") or [])
            for s in svc.get("slots", []) if s.get("is_categorical")}
    intents = []
    for it in svc["intents"]:
        req = list(it.get("required_slots") or [])
        if not req:
            # An intent with no required slots has no checklist, so there is nothing here for this
            # kit to be right or wrong about. Skipped loudly rather than shipped as an empty row.
            print("  skipped %s — no required_slots, so no checklist" % it["name"])
            continue
        intents.append({"key": it["name"],
                        "label": LABELS.get(it["name"], it["name"]),
                        "required": req,
                        "values": {s: vals[s] for s in req if s in vals},
                        "optional": sorted((it.get("optional_slots") or {}).keys())})
    out = {
        "source": "Schema-Guided Dialogue (SGD), service %s, train split" % SERVICE,
        "url": ("https://github.com/google-research-datasets/"
                "dstc8-schema-guided-dialogue"),
        "licence": ("CC BY-SA 4.0 — read at LICENSE.txt in the source repo on 2026-08-09. The "
                    "dialogues are NOT redistributed by this kit; only these slot names, which "
                    "are the dataset's own schema metadata, and the attribution above."),
        "citation": "Rastogi et al. 2020, Towards Scalable Multi-Domain Conversational Agents.",
        "built_by": "tools/build_corpus.py (parsed from the fetched schema.json; never typed)",
        "intents": intents,
        "states": STATES,
    }
    p = os.path.join(DATA, "slots.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("  slots.json: %d intent(s), %d state(s)" % (len(intents), len(STATES)))
    return out


def _cases(slots):
    """One case per USER turn that leaves the checklist in a state worth judging.

    A case is a conversation PREFIX plus the dialogue state at its end. That state is the gold: the
    dataset records, per turn, exactly which slots have been established and with what values. The
    scorer is therefore pure code and costs nothing to run.

    ⚑ EACH DIALOGUE STOPS AT THE TURN ITS CHECKLIST FIRST FILLS, AND THAT DECISION WAS FORCED BY
    MEASUREMENT. Taking every user turn gave 3,190 cases of which 2,402 — 75% — already had a full
    checklist, because these conversations carry on well past the intake (confirming, booking,
    chatting). On that set "always stop" scores 75% without reading anything, and the number the
    kit reports would mostly be measuring how often the corpus keeps talking.

    The intake task ENDS when the checklist fills. Turns after that are a different job, so they
    are not cases. What remains per dialogue is every incomplete turn plus the one turn where it
    becomes complete — which is the decision the kit exists to get right, on both sides.

    ⚠︎ This is a scoping decision, not a filter for flattering numbers, so `dropped` is counted and
    printed. A cap nobody reports reads as full coverage.
    """
    req_of = {i["key"]: set(i["required"]) for i in slots["intents"]}
    cases, seen, dropped = [], 0, 0
    for name in sorted(os.listdir(FETCHED)):
        if not name.startswith("dialogues_"):
            continue
        for dlg in json.load(open(os.path.join(FETCHED, name), encoding="utf-8")):
            if SERVICE not in dlg.get("services", []):
                continue
            seen += 1
            prefix, closed = [], False
            for turn in dlg["turns"]:
                if closed:
                    dropped += 1 if turn["speaker"] == "USER" else 0
                    continue
                prefix.append({"speaker": turn["speaker"], "utterance": turn["utterance"]})
                if turn["speaker"] != "USER":
                    continue
                frame = next((f for f in turn["frames"] if f.get("service") == SERVICE), None)
                if not frame:
                    continue
                st = frame.get("state") or {}
                intent = st.get("active_intent") or ""
                if intent not in req_of:
                    continue
                filled = {k: v for k, v in (st.get("slot_values") or {}).items()
                          if k in req_of[intent]}
                closed = set(filled) == req_of[intent]
                cases.append({
                    "case_id": "%s#%d" % (dlg["dialogue_id"], len(prefix)),
                    "dialogue_id": dlg["dialogue_id"],
                    "intent": intent,
                    "turns": list(prefix),
                    "gold_slots": filled,
                    "gold_complete": closed,
                    "split": "held-out" if _held_out(dlg["dialogue_id"]) else "sample",
                })
    return cases, seen, dropped


def main():
    svc = _schema()
    if svc is None:
        return 1
    os.makedirs(DATA, exist_ok=True)
    print("checklist ...")
    slots = _write_slots(svc)

    print("cases ...")
    cases, dialogues, dropped = _cases(slots)
    if not cases:
        print("ERROR: no cases built — did tools.fetch_corpus run?", file=sys.stderr)
        return 1
    p = os.path.join(DATA, "gold.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    held = sum(1 for c in cases if c["split"] == "held-out")
    done = sum(1 for c in cases if c["gold_complete"])
    print("  gold.jsonl: %d case(s) from %d %s dialogue(s)" % (len(cases), dialogues, SERVICE))
    print("    held-out %d / sample %d  (hashed, %d%% target)"
          % (held, len(cases) - held, int(HELD_OUT_SHARE * 100)))
    print("    STOP cases %d / KEEP-ASKING cases %d — the decision has both sides, which it "
          "did not before this was scoped" % (done, len(cases) - done))
    print("    %d later user turn(s) dropped: the checklist was already full, so the intake "
          "task was over and 'ask again?' is no longer the question" % dropped)
    print("\ngold.jsonl is gitignored: it quotes utterances from a CC BY-SA 4.0 dataset.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
