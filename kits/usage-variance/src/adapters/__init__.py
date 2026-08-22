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
    being BUSY from a request being WRONG without parsing an error string."""

    def __init__(self, msg, status=None, transport=False):
        super().__init__(msg)
        self.status = status
        # True when the request never became an HTTP response at all -- a DNS failure, a refused
        # connection, or a TLS handshake that timed out. See TRANSPORT_ERRORS below for why that
        # is a separate flag rather than another entry in the status list.
        self.transport = transport


# ⚑ TRANSIENT vs TERMINAL. 429 and 5xx mean "ask again shortly"; 400/401/403/404 mean "asking
# again will fail identically and cost you the same". Retrying the second kind is how a bad key
# turns into a rate-limit ban.
TRANSIENT = {408, 429, 500, 502, 503, 504}
RETRIES = 4

# ⚑ AND A CONNECTION THAT NEVER BECAME A RESPONSE IS TRANSIENT TOO — added 2026-08-22, AFTER THIS
# KIT'S OWN SECOND SCORED RUN LOST A DOCUMENT TO IT.
#
# The retry policy above keys entirely on an HTTP STATUS CODE, which means it only ever sees
# failures the server got far enough to name. Run r002-usage-variance lost TLV-0014 to
# `<urlopen error _ssl.c:1011: The handshake operation timed out>` — a TLS handshake that never
# completed, so there was no status, no `HTTPError`, and nothing for `exc.status in TRANSIENT` to
# match. It propagated straight out of the adapter and the harness recorded a failed document, on
# a run where the model itself got every single cell right.
#
# ⚠︎ THE PUBLISHED r002 STILL CARRIES THAT LOSS, AND DELIBERATELY. This branch was written after
# the run, not before it, so r002's coverage is 54 of 55 and the page says so rather than quietly
# re-firing one document into a finished result file. What the fix is NOT is measured: no live
# handshake timeout has been reproduced against it, so it is reasoned from the traceback and the
# same "asking again shortly is the right move" test the status list above already passes.
#
# ⚠︎ IT IS STILL BOUNDED, AND IT IS STILL NOT A SECOND ATTEMPT AT THE TASK. A handshake that timed
# out returned no completion and was billed for nothing, so asking again is finishing the first
# attempt. `URLError` covers DNS failures and connection resets as well as timeouts; all three are
# "the network did not carry the question", none of them is "the question was wrong".
TRANSPORT_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError)


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
    except TRANSPORT_ERRORS as e:
        # status stays None — there was no HTTP response to have one. `transport=True` is what the
        # retry loop reads, so a caller can still tell "the network failed" from "the server said
        # no" without parsing an error string.
        err = AdapterError("transport failure before any HTTP response: %s" % e, status=None)
        err.transport = True
        raise err


def openai_compatible(cfg, system, user, max_tokens, thinking=None):
    """Covers every provider that speaks the OpenAI chat-completions shape -- OpenAI itself,
    Groq, Together, Mistral, xAI, and any local server (Ollama, LM Studio, vLLM).
    BASE_URL is what selects between them, which is why it is in .env rather than in here.

    `thinking` is sent ONLY when the caller passes one, and is passed through verbatim. Omitted,
    the request is byte-identical to what it was before this parameter existed -- so every run
    already recorded stays comparable to a future run that also omits it.
    """
    payload = {"model": cfg["model"], "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    # ⚑ NOT A DEFAULT, AND NOT GUESSED AT. See THINKING_OFF below for the shape and where it came
    # from. A sibling kit in this series lost four documents to replies cut off exactly at their
    # own output ceiling, and the answer turned out to be a reasoning pass nobody asked for. This
    # is the knob that tests it. This kit's own harness never passes it -- see the note on
    # MAX_TOKENS in src/extract.py, which was MEASURED against a real reply rather than guessed --
    # so every run recorded here is byte-identical to what it would have been before this
    # parameter existed.
    if thinking is not None:
        payload["thinking"] = thinking
    body = _post(cfg["base_url"].rstrip("/") + "/chat/completions",
                 {"authorization": "Bearer " + cfg["api_key"]}, payload)
    usage = body.get("usage") or {}
    choice = body["choices"][0]
    return {"text": choice["message"]["content"],
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            # ⚑ THE PROVIDER SAYS WHY IT STOPPED — RECORD IT. A sibling kit's four lost documents
            # each reported output tokens exactly at their cap, and the question that left open
            # ("why does an eleven-field record run to that many tokens?") had been half-answered
            # in this field the whole time, with nothing reading it.
            "finish_reason": choice.get("finish_reason"),
            # ⚑ WHERE THE BUDGET WENT. `finish_reason` says the reply was cut off; this says what
            # ate it. A sibling kit added the same field and it turned a hypothesis into a number
            # in one run -- a median of 100% of that kit's ceiling was a reasoning pass nobody
            # asked for. Absent on providers that do not report it, which is the third state and
            # not a zero.
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


# The one shape this kit will send, taken verbatim from the configured provider's own documented
# request example. Named rather than spelled inline at the call site so there is exactly one place
# a provider's documented field lives, and so a run record can say which one it used.
THINKING_OFF = {"type": "disabled"}


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
    # ⚑ A BUSY PROVIDER IS NOT A FAILED DOCUMENT — added 2026-08-03 in a sibling kit, mid-run,
    # after a live 503 "Service is too busy" dropped a document from a paid run of 57.
    #
    # ⚠︎ THIS DOES NOT WEAKEN "RUN ONCE". Run-once is a claim about how many times the TASK was
    # attempted and published, not about how many TCP requests it took to get one answer. A 503
    # returns no completion, so nothing was extracted and nothing was billed; asking again is
    # finishing the first attempt, not taking a second one. What would break the claim is
    # re-running a document that already answered, and that is not what happens here.
    #
    # Bounded and backed off, because the failure mode on the other side is a provider under load:
    # 1s, 2s, 4s, 8s, then give up and let the caller RECORD the failure as it does today. The same
    # loop now covers a request that never reached the provider at all -- see TRANSPORT_ERRORS.
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
            retryable = (exc.status in TRANSIENT) or getattr(exc, "transport", False)
            if not retryable or attempt == RETRIES:
                raise
            last = exc
            time.sleep(2 ** attempt)
    raise last
