"""Read .env. No dependency, and no key ever leaves this machine.

python-dotenv is a fine library and this is eight lines, so the kit does not ask a forker to
install one to read five variables. The file is gitignored from the first commit; this repo has
never held a credential and is not able to.
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(HERE, ".env")


def load():
    """.env first, then the real environment, which wins. That order is what lets CI and a
    container override a checked-out .env without editing it."""
    cfg = {}
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.update({k: v for k, v in os.environ.items() if k in
                ("PROVIDER", "BASE_URL", "API_KEY", "MODEL", "EMBED_MODEL")})
    return {"provider": cfg.get("PROVIDER", "openai-compatible"),
            "base_url": cfg.get("BASE_URL", ""),
            "api_key": cfg.get("API_KEY", ""),
            "model": cfg.get("MODEL", ""),
            "embed_model": cfg.get("EMBED_MODEL", "")}


def has_key(cfg=None):
    """The kit must render real recorded results with no key configured. Everything that needs one
    checks here first and says so plainly rather than failing at the HTTP layer."""
    return bool((cfg or load()).get("api_key"))
