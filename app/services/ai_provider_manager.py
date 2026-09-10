"""Provider selection, bounded retry/backoff, and failover for "Ask RSE Market".

This module owns *which* AI provider answers a question and what happens when
one fails -- nothing else. It knows nothing about Gemini, OpenAI, RSE tools, or
the database: app/services/ai_assistant.py builds a small, priority-ordered
list of Provider objects (one per configured Gemini/OpenAI tier) and hands
them to answer_with_failover(). Every provider ultimately runs the exact same
RSE tool-calling loop in ai_assistant.py against
app/services/rse_query_tools.py, so failover only ever changes which AI does
the talking -- never how the data is looked up.

Failover triggers ONLY on a genuine AI/provider failure -- the provider's
`call` raising ProviderFailure. A normal answer, including a valid "no
verified data available" result, is a successful return value, not an
exception, so it stops the chain right there and never reaches another
provider.
"""

import logging
import random
import time

logger = logging.getLogger("rse_intelligence.assistant.providers")

# Bounded: a handful of quick, backed-off attempts per provider, never
# indefinite retries.
MAX_ATTEMPTS_PER_PROVIDER = 3
BASE_DELAY_SECONDS = 0.3
MAX_DELAY_SECONDS = 2.0


class ProviderFailure(Exception):
    """Raised by a Provider's `call` for any AI/provider-side failure --
    network error, timeout, rate limit, server overload, bad/missing
    credentials, etc.

    `retryable` controls whether the same provider is retried (bounded, with
    backoff) before failover moves on to the next provider -- temporary
    conditions like 429/502/503/UNAVAILABLE/RESOURCE_EXHAUSTED/timeouts should
    set this True; permanent ones (bad request, auth failure) should not.
    `reason` is an optional short machine code (e.g. "RESOURCE_EXHAUSTED",
    "UNAVAILABLE") the caller can use to choose a specific safe user-facing
    message -- it must never carry vendor/billing detail itself.
    """

    def __init__(self, message, *, retryable=False, reason=None):
        super().__init__(message)
        self.retryable = retryable
        self.reason = reason


class NoProviderConfigured(Exception):
    """None of the providers in the priority list have credentials set."""


class AllProvidersFailed(Exception):
    """Every configured provider was tried (with retries) and failed."""

    def __init__(self, last_failure=None):
        super().__init__("All configured AI providers failed")
        self.last_failure = last_failure


class Provider:
    """One configured, priority-ordered AI provider/model.

    `call` is a zero-argument callable supplied by the caller -- a closure
    over the question and that provider's own client/model -- that runs one
    full answer attempt and returns the {"answer", "sources", "used_tools"}
    result dict, or raises ProviderFailure.
    """

    __slots__ = ("name", "configured", "call")

    def __init__(self, name, configured, call):
        self.name = name
        self.configured = configured
        self.call = call


def _sleep_with_backoff(attempt):
    delay = min(BASE_DELAY_SECONDS * (2 ** (attempt - 1)), MAX_DELAY_SECONDS)
    time.sleep(delay + random.uniform(0, delay * 0.25))


def _try_provider(provider):
    """Bounded retries with short exponential backoff for one provider.
    Returns the successful result, or raises the last ProviderFailure once
    retries are exhausted or the failure is marked non-retryable."""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS_PER_PROVIDER + 1):
        try:
            return provider.call()
        except ProviderFailure as exc:
            last_error = exc
            logger.warning(
                "Ask RSE Market provider %r attempt %d/%d failed (retryable=%s): %s",
                provider.name, attempt, MAX_ATTEMPTS_PER_PROVIDER, exc.retryable, exc,
            )
            if not exc.retryable or attempt == MAX_ATTEMPTS_PER_PROVIDER:
                break
            _sleep_with_backoff(attempt)
    raise last_error


def answer_with_failover(providers):
    """Try each configured provider in priority order, with bounded retries
    per provider, falling over to the next provider only on a genuine
    AI/provider failure. Returns the first successful result dict.

    Raises NoProviderConfigured if none of the providers have credentials
    set, or AllProvidersFailed (carrying the last ProviderFailure) if every
    configured provider was tried and exhausted its retries.
    """
    attempted = False
    last_failure = None
    for provider in providers:
        if not provider.configured:
            continue
        attempted = True
        try:
            return _try_provider(provider)
        except ProviderFailure as exc:
            last_failure = exc
            logger.error("Ask RSE Market provider %r exhausted retries, failing over", provider.name)
            continue

    if not attempted:
        raise NoProviderConfigured()
    raise AllProvidersFailed(last_failure)
