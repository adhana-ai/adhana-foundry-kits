"""SEAM 1 — the model. Swapping provider or model is .env plus the same run again.

THIS IS THE TEACHING POINT OF THE KIT, not the app above it. It makes one claim checkable that
everybody asserts and nobody demonstrates: swapping models is a one-line change, and knowing
whether you should is an eval run.

WHY RAW HTTP FOR EVERY PROVIDER, INCLUDING ANTHROPIC.
Each vendor ships an excellent official SDK, and for a single-vendor application you should use
it. This is not a single-vendor application. A forker runs this on whichever provider they already
hold a key for, so giving one vendor its SDK and the rest a hand-rolled client would bake a
preference into the exact file whose purpose is not having one -- and it would make `pip install`
pull a client for a vendor most forkers will never call. The wire format for a single completion
is small enough that stdlib is honestly the right size, and it keeps the fork test to one install.

Adding a provider is one function and one entry in PROVIDERS. It must return the same shape,
including token counts -- lens 05 publishes them and lens 07 prices them, so a provider that
returns no usage cannot be published.
"""
import json
import time
import urllib.error
import urllib.request

from .. import budget


class AdapterError(RuntimeError):
    """`status` is the HTTP code when there was one, else None — so a caller can tell a provider
    being BUSY from a request being WRONG without parsing an error string.

    ⚑ `transport` IS THE THIRD STATE, AND THIS KIT PAID FOR IT LIVE. A socket-level failure — a
    read that times out, a connection reset — never reaches an HTTP status at all, so `status` is
    None and a retry policy written only around status codes lets it through as terminal. Run
    r001-partlife-recon lost REC-0029 to `<urlopen error [Errno 60] Operation timed out>` on call
    43 of 50: no completion came back, nothing was extracted, and the document was recorded as a
    failure that looks on a results page exactly like a model that could not do the task. It was
    not. `transport` is what lets the loop below tell the two apart.
    """

    def __init__(self, msg, status=None, transport=False):
        super().__init__(msg)
        self.status = status
        self.transport = transport


# ⚑ TRANSIENT vs TERMINAL. 429 and 5xx mean "ask again shortly"; 400/401/403/404 mean "asking
# again will fail identically and cost you the same". Retrying the second kind is how a bad key
# turns into a rate-limit ban.
TRANSIENT = {408, 429, 500, 502, 503, 504}
RETRIES = 4


def _post(url, headers, payload, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # The body carries the actual reason. Raising the status alone turns "your key is for a
        # different model" into "400", which is the kind of error message that costs an afternoon.
        raise AdapterError("%s %s: %s" % (e.code, e.reason, e.read().decode("utf-8", "replace")),
                           status=e.code)
    # ⚠︎ HTTPError IS A SUBCLASS OF URLError, so this clause must come second or it would swallow
    # every real HTTP status and report a 401 as a network problem.
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AdapterError("transport failure before any HTTP status: %r" % (e,), transport=True)


def openai_compatible(cfg, system, user, max_tokens, thinking=None):
    """Covers every provider that speaks the OpenAI chat-completions shape -- OpenAI itself,
    DeepSeek, Groq, Together, Mistral, xAI, and any local server (Ollama, LM Studio, vLLM).
    BASE_URL is what selects between them, which is why it is in .env rather than in here.

    `thinking` is sent ONLY when the caller passes one, and is passed through verbatim. Omitted,
    the request is byte-identical to what it was before this parameter existed -- so every run
    already recorded stays comparable to a future run that also omits it.
    """
    payload = {"model": cfg["model"], "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    # ⚑ NOT A DEFAULT, AND THIS KIT NEVER PASSES ONE. The parameter exists for a forker whose
    # provider documents a reasoning-off shape and who wants to test it; partlife-recon's own
    # harness omits it on every call, so the request is byte-identical to what it would be if this
    # parameter did not exist -- which is what keeps r001 and r002 comparable to any future run
    # that also omits it. There was no output-budget question to investigate here: MAX_TOKENS was
    # measured on both tiers before either scored run and the longest reply came in at 976 of 2,000.
    if thinking is not None:
        payload["thinking"] = thinking
    body = _post(cfg["base_url"].rstrip("/") + "/chat/completions",
                 {"authorization": "Bearer " + cfg["api_key"]}, payload)
    usage = body.get("usage") or {}
    choice = body["choices"][0]
    return {"text": choice["message"]["content"],
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            # ⚑ THE PROVIDER SAYS WHY IT STOPPED — RECORD IT. evals/measure_cap.py reads exactly
            # this field to tell "the reply was this long" from "the ceiling was this low": a probe
            # where every reply finishes on `stop` has measured the REPLY, and one where anything
            # finishes on `length` has measured the CEILING and has to be repeated higher. Without
            # it, MAX_TOKENS would be a guess with a plausible-looking number beside it.
            "finish_reason": choice.get("finish_reason"),
            # ⚑ WHERE THE BUDGET WENT. `finish_reason` says the reply was cut off; this says what
            # ate it -- a reasoning pass nobody asked for shows up here and nowhere else. Recorded
            # by evals/measure_cap.py on every probe. On this kit's five probe calls it came back
            # empty on both tiers, which is consistent with replies of 466-976 tokens for a
            # thirteen-key JSON object and no hidden pass. Absent on providers that do not report
            # it, which is the third state and not a zero.
            "token_details": (usage.get("completion_tokens_details")
                              or usage.get("output_tokens_details")),
            "raw": body}


def anthropic(cfg, system, user, max_tokens):
    """Anthropic's Messages API. Three things differ from the shape above and all three bite:
    the key rides `x-api-key` rather than a bearer header, `anthropic-version` is required, and
    the system prompt is its own top-level field instead of a message with role 'system'."""
    body = _post((cfg.get("base_url") or "https://api.anthropic.com").rstrip("/") + "/v1/messages",
                 {"x-api-key": cfg["api_key"], "anthropic-version": "2023-06-01"},
                 {"model": cfg["model"], "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]})
    usage = body.get("usage") or {}
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    return {"text": text,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            # Anthropic spells the same fact "max_tokens" rather than "length". Normalised here so
            # a caller can test one value across both providers, which is this module's whole job.
            "finish_reason": {"max_tokens": "length"}.get(body.get("stop_reason"),
                                                          body.get("stop_reason")),
            "raw": body}


PROVIDERS = {"openai-compatible": openai_compatible, "anthropic": anthropic}


# ⚑ NO `THINKING_OFF` CONSTANT HERE, AND ITS ABSENCE IS DELIBERATE. Sibling kits in this series
# carry one — a named copy of one provider's documented reasoning-off request shape — because they
# had a reason to test it. This kit never sends a `thinking` field at all: MAX_TOKENS was measured
# on both tiers before either run (see src/extract.py) and no reply came anywhere near the ceiling,
# so there was no output-budget question to investigate and nothing to disable. A named constant
# holding one vendor's field name, unused, is a vendor preference sitting in the one file whose
# whole job is not having one. The `thinking` parameter below still exists for a caller that wants
# it; this kit's own harness never passes one, and LLM.settings on the published page says so.


def complete(cfg, system, user, max_tokens=1024, thinking=None):
    """`thinking` is passed through to the provider untouched, or omitted entirely when None.

    ⚠︎ PROVIDER-SPECIFIC, AND NOT SILENTLY SWALLOWED. Only the OpenAI-compatible path accepts it,
    because that is the only shape whose documentation this kit has read. Sending it to Anthropic
    would be inventing a field on a provider nobody checked -- so it is refused loudly rather than
    dropped, which would leave a run believing it had disabled something it had not.
    """
    name = cfg.get("provider")
    if thinking is not None and name != "openai-compatible":
        raise AdapterError(
            "thinking=%r was requested but provider %r has no documented field for it in this "
            "kit. Dropping it silently would let a run record claim a setting it never sent."
            % (thinking, name))
    if name not in PROVIDERS:
        raise AdapterError("unknown PROVIDER %r -- known: %s. Add one in src/adapters/__init__.py"
                           % (name, ", ".join(sorted(PROVIDERS))))
    if not cfg.get("api_key"):
        raise AdapterError("no API_KEY set. Copy .env.example to .env -- or run the offline path, "
                           "which needs no key and renders the recorded results.")
    if not cfg.get("model"):
        raise AdapterError("no MODEL set. There is no default on purpose: a kit that picks a model "
                           "for you has picked your bill and your latency too.")
    # ⚑ A BUSY PROVIDER IS NOT A FAILED DOCUMENT — added 2026-08-03, mid-run, after a live
    # 503 "Service is too busy" dropped a document from a paid run of 57.
    #
    # ⚠︎ THIS DOES NOT WEAKEN "RUN ONCE". Run-once is a claim about how many times the TASK was
    # attempted and published, not about how many TCP requests it took to get one answer. A 503
    # returns no completion, so nothing was extracted and nothing was billed; asking again is
    # finishing the first attempt, not taking a second one. What would break the claim is
    # re-running a document that already answered, and that is not what happens here.
    #
    # Bounded and backed off, because the failure mode on the other side is a provider under load:
    # 1s, 2s, 4s, 8s, then give up and let the caller RECORD the failure as it does today.
    # ⚑ THE DAILY CAP IS CHECKED HERE, NOT IN THE RUN HARNESS — added 2026-08-04.
    #
    # One key funds every kit, and this is the only line all of them go through: the eval harness,
    # the local app, a screenshot script, and whatever a forker writes next. Putting the guard in
    # `evals/run.py` would cap the run that already prints what it is about to spend and leave
    # every other caller uncapped — including the app, which spends one call per click with
    # nothing counting them at all. A second place to remember is a place to forget.
    #
    # It is checked ONCE per completion rather than once per HTTP attempt, because a retried 503
    # returns no completion and is billed for none: charging the budget for it would make a busy
    # provider look like spending, which is exactly the confusion the retry comment above settles.
    budget.check(1)
    budget.record(cfg.get("model"))

    last = None
    for attempt in range(RETRIES + 1):
        try:
            # `thinking` reaches the provider only where it is accepted; the guard above already
            # refused every other path loudly, so passing it here cannot reach a provider that
            # would ignore it.
            if thinking is not None:
                return PROVIDERS[name](cfg, system, user, max_tokens, thinking=thinking)
            return PROVIDERS[name](cfg, system, user, max_tokens)
        except AdapterError as exc:
            # ⚑ A TRANSPORT FAILURE IS TRANSIENT TOO — added after run r001-partlife-recon lost a
            # document to a socket timeout that never became an HTTP status. See AdapterError.
            #
            # ⚠︎ AND IT IS NOT QUITE THE SAME AS A 503, WHICH IS WORTH SAYING RATHER THAN GLOSSING.
            # A 503 is the provider telling you it did nothing. A client-side timeout is the
            # CLIENT giving up: the provider may well have completed the work and billed for it,
            # and the retry is then a second billed completion the ledger below counts as one.
            # That is a real, small under-count on this path, recorded here rather than hidden —
            # the alternative is losing the document, which costs a whole record.
            if not (exc.status in TRANSIENT or exc.transport) or attempt == RETRIES:
                raise
            last = exc
            time.sleep(2 ** attempt)
    raise last
