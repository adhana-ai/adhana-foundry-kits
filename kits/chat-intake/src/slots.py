"""The checklist, read from data/slots.json. One source, and everything reads it from here.

⚑ THE PROMPT, THE PIPELINE, THE SCORER AND THE BASELINE ALL IMPORT THIS MODULE. That is the same
discipline docs-route's taxonomy.py states for its queues, and it exists because the alternative is
a checklist that drifts: a slot added to the prompt and not to the scorer produces a model that
answers correctly and is marked wrong, which is the most expensive kind of bug to chase because
both halves look right on their own.

⚠︎ AND THE FILE IS DERIVED, NOT AUTHORED. tools/build_corpus.py parses it out of the dataset's own
schema.json. Editing data/slots.json by hand would make this kit grade a model against our opinion
of what a bank transfer needs while claiming to grade it against the dataset's. If a slot looks
wrong, it is wrong upstream — go and look.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(HERE, "data", "slots.json")


class NotBuilt(RuntimeError):
    """data/slots.json is absent. Raised with the command that fixes it, because the fix is one
    line and a bare FileNotFoundError sends people reading source instead of typing it."""


def load():
    if not os.path.exists(PATH):
        raise NotBuilt(
            "data/slots.json is not built yet. This kit's corpus is CC BY-SA 4.0 and is fetched "
            "rather than committed, so a fresh clone has to build it once:\n"
            "    python3 -m tools.fetch_corpus\n"
            "    python3 -m tools.build_corpus")
    with open(PATH, encoding="utf-8") as fh:
        return json.load(fh)


def intents():
    """{intent key: [required slot, ...]} — the whole checklist, keyed the dataset's way."""
    return {i["key"]: list(i["required"]) for i in load()["intents"]}


def required(intent):
    """The facts one intent has to collect. An unknown intent is an empty checklist rather than a
    KeyError: the model may answer with a name nobody defined, and that is a wrong answer to score,
    not a crash to debug."""
    return intents().get(intent, [])


def states():
    """The four states the panel and the report share. Authored, unlike the checklist."""
    return load()["states"]


def missing(intent, collected):
    """What is still owed. Deterministic, and this is the whole 'know when you have enough' test —
    the kit's decision is `not missing(...)`, computed here rather than asked of the model."""
    return [s for s in required(intent) if s not in (collected or {})]
