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
import http.client
import json
import time
import urllib.error
import urllib.request

from .. import budget


class AdapterError(RuntimeError):
    """`status` is the HTTP code when there was one, else None — so a caller can tell a provider
    being BUSY from a request being WRONG without parsing an error string.

    `transport` is True when the request never got far enough to HAVE a status: a connection reset,
    a socket timeout, a DNS failure, a half-read body. See the TRANSPORT note below — that
    distinction cost a sibling kit in this series two documents of a paid run before it existed,
    and this kit ships it from birth rather than paying for it again.
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
    # ⚑ A DROPPED CONNECTION IS NOT A FAILED DOCUMENT EITHER — and this kit ships that clause from
    # birth rather than learning it. A SIBLING KIT IN THIS SERIES PAID FOR IT: its first paid run
    # of 55 documents lost TWO outright, one to `<urlopen error [Errno 60] Operation timed out>`
    # and one to `[Errno 54] Connection reset by peer`, and its superseded pass is committed rather
    # than deleted. ⚠︎ THE CONSEQUENCE ON THIS KIT IS SPECIFIC: a lost case has no verdict, and a
    # proposed application with no verdict is indistinguishable from one nobody checked.
    #
    # ⚠︎ THE RETRY LOOP BELOW ONLY EVER SAW `AdapterError`, AND ONLY EVER LOOKED AT ITS STATUS.
    # A transport failure raises a bare OSError out of urlopen, which is not an AdapterError at
    # all, so it flew straight past four perfectly good backoff attempts and out to the harness,
    # which recorded it as a failed document. The sibling comment further down already argues that
    # a BUSY PROVIDER is not a failed document; a DROPPED CONNECTION is the same argument one
    # layer lower, and the code only implemented the top half of it.
    #
    # `urllib.error.URLError` and `ConnectionResetError` are both OSError subclasses, and
    # HTTPError -- which IS a URLError -- is caught above, so this cannot swallow a real status.
    # `http.client.HTTPException` covers a body that died mid-read (RemoteDisconnected,
    # IncompleteRead), which returns no completion and is billed for none, exactly like a 503.
    except (OSError, http.client.HTTPException) as e:
        raise AdapterError("transport failure talking to the provider: %s" % e, transport=True)


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
    # ⚑ NOT A DEFAULT, AND NOT GUESSED AT. See THINKING_OFF below for the shape and where it came
    # from. Sibling kits in this series measured provider-side reasoning at three quarters of their
    # output tokens on a reply that is a couple of hundred tokens of actual JSON, so "what does
    # turning it off cost in accuracy" is a real question with a real bill attached. THIS KIT'S
    # HARNESS NEVER SENDS IT, and the run record says `thinking: null` rather than leaving the
    # field out -- a run that does not record the setting is indistinguishable from one that sent
    # it. Answering the question needs another paid run and this kit did not fire one.
    if thinking is not None:
        payload["thinking"] = thinking
    body = _post(cfg["base_url"].rstrip("/") + "/chat/completions",
                 {"authorization": "Bearer " + cfg["api_key"]}, payload)
    usage = body.get("usage") or {}
    choice = body["choices"][0]
    return {"text": choice["message"]["content"],
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            # ⚑ THE PROVIDER SAYS WHY IT STOPPED — RECORD IT. A sibling kit spent three runs
            # publishing "failures" that were nothing but a truncated reply against a cap set from
            # a smaller corpus; the API had been answering half of that in this field the whole
            # time and nothing read it. evals/run.py branches on it before it calls anything a
            # failure.
            "finish_reason": choice.get("finish_reason"),
            # ⚑ WHERE THE BUDGET WENT. `finish_reason` says the reply was cut off; this says what
            # ate it. On sibling kits in this series a median of three quarters of the output
            # tokens was a reasoning pass nobody asked for. Absent on providers that do not report
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


# The one shape this kit would send if a caller asked for it, taken verbatim from the request
# example the configured provider publishes for its own model. Named rather than spelled inline
# at the call site so there is exactly one place a provider's documented field lives, and so a
# run record can say which one it used. ⚠︎ THIS KIT NEVER SENDS IT -- see the note in
# openai_compatible() above; nothing here has measured what disabling reasoning costs.
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
    # ⚑ A BUSY PROVIDER IS NOT A FAILED DOCUMENT — inherited from a sibling kit that learned it
    # mid-run, when a live 503 "Service is too busy" dropped a document from a paid pass.
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
            # ⚑ `or exc.transport` IS THE HALF THAT WAS MISSING. A reset connection and a socket
            # timeout have no status to test, so `exc.status not in TRANSIENT` was True for both
            # and the loop re-raised on the first attempt. Two documents of a sibling kit's paid
            # 55 were lost to exactly that before this clause existed anywhere in the repo.
            if not (exc.status in TRANSIENT or exc.transport) or attempt == RETRIES:
                raise
            last = exc
            time.sleep(2 ** attempt)
    raise last
