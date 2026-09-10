""""Ask RSE Market" — the natural-language layer over app/services/rse_query_tools.py.

Architecture (spec): User Question -> AI Intent Understanding -> Backend RSE
Query Tools -> Validated Database -> Calculations/Validation -> AI Explanation
-> Answer + Source.

The model is never given market data to work from and is never allowed to
answer a data question without calling a tool first — the only way it can
learn a real figure is by calling one of the functions in
app/services/rse_query_tools.py, each of which reads straight from the
platform's own canonical (approved-report) database and returns an explicit
"not found" rather than ever letting a gap be filled in. This module's job is
purely to run that tool-calling loop and turn the results into a plain-English
explanation — it holds no market data of its own, and every source shown to
the user is built from the tool results returned during the loop below, not
from the model's own prose.

Multi-provider failover: Gemini (primary) -> Gemini (optional backup
project/key) -> OpenAI (final fallback) -> safe generic error. Every provider
runs the *same* tool-calling loop against the *same* RSE tools below -- only
which AI is doing the talking changes. Provider selection, bounded
retry/backoff, and failover live in app/services/ai_provider_manager.py so
that logic isn't duplicated per provider; this module owns the prompt, the
tool schemas, the RSE tool-execution loop (once per SDK shape), and turning a
final failure into a safe, generic, no-internal-detail message.
"""

import json
import logging

import openai
from flask import current_app
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.services import ai_provider_manager as provider_manager
from app.services import rse_query_tools as tools

logger = logging.getLogger("rse_intelligence.assistant")

MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """You are "Ask RSE Market", a market-intelligence analyst assistant for the \
RSE Intelligence platform (Rwanda Stock Exchange). You help Administrator and Analyst users \
understand the platform's own verified market data. You write like a professional market \
intelligence analyst producing a report for investors, regulators, and researchers — not like \
a general-purpose chatbot.

DATA-INTEGRITY RULES (never break these):
1. You have NO market knowledge of your own. Never state a price, volume, index \
value, exchange rate, bond figure, or any other RSE market fact unless it came \
from a tool call you just made in this conversation. If you have not called a \
tool for a fact, you do not know it.
2. If a tool result says a value was not found or is missing, say so plainly \
("no verified data is available for X" / "this could not be verified") — never \
guess, estimate, or fill in a plausible-sounding number, and never treat a \
missing value as zero.
3. Always state which report date the figures came from, exactly as given by \
the tool result. Only call a report "the latest" if the tool result confirms it \
is the latest VERIFIED report — if the most recent report is not yet verified, \
say so explicitly instead.
4. Clearly separate observed data (what the report states), calculated values \
(differences, rankings — always computed by the tools, never by you), and your \
own brief analysis/explanation.
5. Never invent, estimate, round-replace, or otherwise modify a figure returned \
by a tool. Reproduce exact values in tables; a rounded human-readable equivalent \
(e.g. "RWF 6.635 trillion") may be added in parentheses/prose alongside the exact \
figure, never instead of it. Never state a percentage, trend, or comparison that \
isn't directly supported by the tool data.
6. Do not give investment advice, buy/sell recommendations, or personalized \
financial guidance. You may describe what the data shows; you must not tell the \
user what to do about it.
7. If the question is not about RSE market data on this platform, briefly say \
that you can only help with verified RSE market data and suggest what you can \
answer instead.

RESPONSE FORMAT (apply consistently, adapting structure to the question):
- Answer the question directly in the first sentence.
- Use Markdown: `####` for section headings, `**bold**` for labels/key figures, \
and GitHub-style `| ... |` tables whenever multiple related metrics are being \
presented or compared. Bullet lists (`* `) for short takeaways.
- Format every Rwanda Franc amount as "RWF" plus the exact comma-separated figure \
from the tool result (e.g. "RWF 220,993,000"). For very large amounts you may add \
a readable equivalent in parentheses/prose (e.g. "RWF 6,634,919,683,716 (RWF 6.635 \
trillion)") but the exact figure must still appear, typically in the table.
- Clearly distinguish equity figures, bond figures, and combined/total market \
figures — never blend them without labeling which is which.
- Whenever a report is referenced, state its report date and verification status; \
mention the Report ID when useful for traceability. If verified, say so explicitly \
("verified RSE report"); if not verified / not found, say the data could not be \
verified rather than presenting it as fact.
- For a market overview: an executive-summary opening sentence, a "Market Snapshot" \
table of the key statistics, then a short "Key Takeaways" bullet list.
- For a single security (equity/bond/currency): open with a company/security \
snapshot sentence, then its trading metrics (table if there are several), \
prioritizing that security's own data over generic market context.
- For a comparison ("compare X and Y"): use a side-by-side comparison table plus a \
short analysis paragraph, citing the tool-computed differences (never compute \
your own).
- For a historical/trend question: a chronological table (oldest to newest) \
followed by a brief, data-grounded description of the movement.
- For bonds: present maturity, tenor, coupon, and yield/price fields the tool \
returns, clearly labeled.
- Close with a short "Key Takeaway" line instead of a conversational sign-off, \
when a closing observation adds value.
- Keep responses concise, non-repetitive, and free of filler.

TONE: Write like a market intelligence analyst. Prefer phrasing such as "The latest \
verified RSE report indicates...", "Trading activity was concentrated in...", \
"Equity turnover amounted to...", "Bond trading accounted for...", "The combined \
turnover reached...". Never use chatbot phrasing like "Here's what I found!", \
"Great question!", "Sure!", emojis, casual language, or unnecessary disclaimers.
"""

TOOL_SECTION_LABELS = {
    "get_latest_report_status": "Report Status",
    "get_market_overview": "Market Overview",
    "get_equity": "Equities",
    "get_equity_history": "Equities (Historical)",
    "compare_equities": "Equities",
    "top_performers": "Equities",
    "get_indices": "Indices",
    "get_bonds": "Bonds",
    "get_bond_trades": "Bond Trades",
    "get_exchange_rates": "Exchange Rates",
    "get_exchange_rate_history": "Exchange Rates (Historical)",
}

# Tool schemas, in plain {name, description, parameters} form (parameters is a
# JSON Schema object). Fed to the Gemini SDK below via FunctionDeclaration's
# parameters_json_schema, which accepts this exact shape directly.
TOOL_SCHEMAS = [
    {
        "name": "get_latest_report_status",
        "description": "Get whether the most recently uploaded RSE report is fully verified "
                        "(approved), and what the latest verified report is if not. Use this "
                        "for any question about report/data verification status.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_market_overview",
        "description": "Get overall market statistics (shares traded, turnover, market cap), "
                        "indices, and exchange rates for the latest verified report, or a "
                        "specific one by report_id.",
        "parameters": {
            "type": "object",
            "properties": {"report_id": {"type": "integer", "description": "Optional specific report id."}},
            "required": [],
        },
    },
    {
        "name": "get_equity",
        "description": "Get the latest verified snapshot (price, change, volume, etc.) for one "
                        "equity by its symbol, e.g. 'BLR' or 'BOK'.",
        "parameters": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Equity ticker symbol."}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_equity_history",
        "description": "Get verified historical closing prices for one equity symbol across "
                        "past reports, oldest to newest.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "limit": {"type": "integer", "description": "Max number of past reports, default 10."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "compare_equities",
        "description": "Compare the latest verified snapshots of two or more equities side by "
                        "side, including a backend-computed price/volume difference.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "Two or more ticker symbols."},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "top_performers",
        "description": "Rank equities in one verified report by a metric, e.g. to answer "
                        "'which equity had the highest trading volume'.",
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "enum": ["volume", "change_percent", "value_turnover"]},
                "limit": {"type": "integer", "description": "How many to return, default 5."},
                "report_id": {"type": "integer"},
            },
            "required": ["metric"],
        },
    },
    {
        "name": "get_indices",
        "description": "Get RSE index values (e.g. RSI, ALSI) and their change for the latest "
                        "verified report, or a specific one.",
        "parameters": {
            "type": "object",
            "properties": {"report_id": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "get_bonds",
        "description": "Get government/corporate bond listings for the latest verified report, "
                        "or a specific one.",
        "parameters": {
            "type": "object",
            "properties": {
                "bond_type": {"type": "string", "enum": ["government", "corporate"]},
                "report_id": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "get_bond_trades",
        "description": "Get recent bond trade activity (price, volume, value) for the latest "
                        "verified report, or a specific one.",
        "parameters": {
            "type": "object",
            "properties": {"report_id": {"type": "integer"}, "limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "get_exchange_rates",
        "description": "Get foreign exchange rates (e.g. USD/RWF) for the latest verified "
                        "report, or a specific one, optionally filtered to one currency.",
        "parameters": {
            "type": "object",
            "properties": {"currency": {"type": "string"}, "report_id": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "get_exchange_rate_history",
        "description": "Get verified historical exchange rates for one currency across past reports.",
        "parameters": {
            "type": "object",
            "properties": {"currency": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["currency"],
        },
    },
]

GEMINI_TOOLS = [
    genai_types.Tool(function_declarations=[
        genai_types.FunctionDeclaration(
            name=schema["name"],
            description=schema["description"],
            parameters_json_schema=schema["parameters"],
        )
        for schema in TOOL_SCHEMAS
    ])
]

# Same TOOL_SCHEMAS, reshaped for OpenAI's function-calling format -- the tool
# definitions themselves are never duplicated, only converted per SDK.
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["parameters"],
        },
    }
    for schema in TOOL_SCHEMAS
]


def _build_gemini_client(api_key):
    # The SDK does not retry at all by default (0 retries) and has no request
    # timeout by default (waits indefinitely). Both left every transient
    # Gemini-side hiccup (503 overload, brief rate-limit bursts, network
    # blips) surface immediately as a hard failure with no resilience.
    # Bound both explicitly: a handful of quick, backed-off retries for the
    # HTTP layer's own retriable statuses (408/429/500/502/503/504), and a
    # ceiling on how long a single request may hang. This is in addition to,
    # not instead of, the provider-level retry/failover in
    # app/services/ai_provider_manager.py, which covers a whole request
    # (including tool-calling rounds), not just one HTTP call.
    return genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(
            timeout=30_000,  # milliseconds
            retry_options=genai_types.HttpRetryOptions(
                attempts=3,
                initial_delay=1.0,
                max_delay=4.0,
            ),
        ),
    )


def _build_openai_client(api_key):
    # max_retries=0: retry/backoff for a whole request is owned exclusively by
    # app/services/ai_provider_manager.py so every provider gets the same,
    # bounded retry behaviour instead of each SDK layering its own on top.
    return openai.OpenAI(api_key=api_key, timeout=30.0, max_retries=0)


def _extract_sources(tool_name, result):
    """Pull every {report_id, ...} reference out of one tool result, tagged
    with which platform section it came from. This is the ONLY place the
    "Source" block shown to the user is built from — it reads the tool's
    actual return value, never the model's text."""
    if not isinstance(result, dict):
        return []
    section = TOOL_SECTION_LABELS.get(tool_name, tool_name)
    refs = []
    if result.get("report"):
        refs.append(result["report"])
    if tool_name == "get_latest_report_status" and result.get("latest_verified_report"):
        refs.append(result["latest_verified_report"])
    if tool_name == "compare_equities":
        for eq in (result.get("equities") or {}).values():
            if isinstance(eq, dict) and eq.get("report"):
                refs.append(eq["report"])
    return [dict(r, section=section) for r in refs]


def _dedupe_sources(sources):
    seen = set()
    deduped = []
    for s in sources:
        key = (s.get("report_id"), s.get("section"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    return deduped


def _execute_tool_call(name, args):
    """Runs one tool call against the existing, unchanged RSE tool layer
    (app/services/rse_query_tools.py). Shared verbatim by every AI provider's
    conversation loop below so the RSE business logic and database access
    path are never duplicated per provider."""
    func = tools.TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"found": False, "message": "That capability is not available."}
    try:
        return func(**args)
    except TypeError:
        # The model passed arguments the tool doesn't accept -- fail closed
        # with an explicit "not found" rather than letting an exception about
        # internal argument shapes reach the user.
        return {"found": False, "message": "That question could not be understood well enough to look up."}


def _run_gemini_conversation(client, model, question):
    """Runs the tool-calling loop for one Gemini provider (primary or
    backup) to completion. Returns the {"answer", "sources", "used_tools"}
    result dict for a normal answer -- including a valid "not found"/"data
    unavailable" tool result, which is a successful answer, not a failure.
    Raises on any AI/provider failure; the caller translates that into a
    ProviderFailure for app/services/ai_provider_manager.py to handle."""
    config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=GEMINI_TOOLS,
        temperature=0.2,
    )
    contents = [genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=question)])]
    sources = []
    used_tools = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(model=model, contents=contents, config=config)
        function_calls = response.function_calls

        if not function_calls:
            return {
                "answer": response.text or "I couldn't generate a response for that question.",
                "sources": _dedupe_sources(sources),
                "used_tools": used_tools,
            }

        contents.append(response.candidates[0].content)

        response_parts = []
        for call in function_calls:
            name, args = call.name, call.args or {}
            result = _execute_tool_call(name, args)
            used_tools.append(name)
            sources.extend(_extract_sources(name, result))

            # Normalize to plain JSON-safe types (e.g. date objects -> strings)
            # before handing the result back to the model.
            safe_result = json.loads(json.dumps(result, default=str))
            response_parts.append(genai_types.Part.from_function_response(name=name, response=safe_result))

        contents.append(genai_types.Content(role="user", parts=response_parts))

    return {
        "answer": "I wasn't able to finish answering that question. Please try rephrasing it, "
                  "or ask about one thing at a time.",
        "sources": _dedupe_sources(sources),
        "used_tools": used_tools,
    }


def _run_openai_conversation(client, model, question):
    """Same tool-calling loop as _run_gemini_conversation, reshaped for
    OpenAI's chat-completions message/tool-call format. Calls the exact same
    _execute_tool_call / _extract_sources helpers -- the RSE tools and the
    database they read from are identical to the Gemini path."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    sources = []
    used_tools = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=OPENAI_TOOLS, temperature=0.2,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls

        if not tool_calls:
            return {
                "answer": message.content or "I couldn't generate a response for that question.",
                "sources": _dedupe_sources(sources),
                "used_tools": used_tools,
            }

        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in tool_calls
            ],
        })

        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}
            result = _execute_tool_call(name, args)
            used_tools.append(name)
            sources.extend(_extract_sources(name, result))

            safe_result = json.loads(json.dumps(result, default=str))
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(safe_result),
            })

    return {
        "answer": "I wasn't able to finish answering that question. Please try rephrasing it, "
                  "or ask about one thing at a time.",
        "sources": _dedupe_sources(sources),
        "used_tools": used_tools,
    }


_RETRYABLE_GEMINI_HTTP_CODES = {408, 429, 500, 502, 503, 504}
_RETRYABLE_GEMINI_STATUSES = {"UNAVAILABLE", "RESOURCE_EXHAUSTED"}


def _classify_gemini_error(exc):
    """Returns (retryable, reason). `reason` is a stable machine-readable code
    (RESOURCE_EXHAUSTED, UNAVAILABLE, ...) parsed from Gemini's own JSON error
    body -- safe to branch on for a more specific user-facing message, never
    leaking vendor/billing detail itself."""
    if isinstance(exc, genai_errors.APIError):
        retryable = exc.code in _RETRYABLE_GEMINI_HTTP_CODES or exc.status in _RETRYABLE_GEMINI_STATUSES
        return retryable, exc.status
    # Anything else reaching here (timeouts, connection resets, DNS blips) is
    # a transient network condition worth a bounded retry.
    return True, None


def _make_gemini_provider(name, api_key, model, question):
    if not api_key:
        return provider_manager.Provider(name=name, configured=False, call=None)

    # Built once per provider and reused across retry attempts -- a client is
    # a reusable connection/config object, not a per-request one, so a
    # transient failure retries the same client rather than paying to
    # reconnect from scratch each time.
    client = _build_gemini_client(api_key)

    def _call():
        try:
            return _run_gemini_conversation(client, model, question)
        except Exception as exc:
            retryable, reason = _classify_gemini_error(exc)
            logger.warning("Ask RSE Market: %s call failed (retryable=%s): %s", name, retryable, exc)
            raise provider_manager.ProviderFailure(str(exc), retryable=retryable, reason=reason) from exc

    return provider_manager.Provider(name=name, configured=True, call=_call)


def _classify_openai_error(exc):
    """Returns (retryable, reason), mirroring _classify_gemini_error."""
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        return True, None
    if isinstance(exc, openai.APIStatusError):
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True, "RESOURCE_EXHAUSTED"
        if status_code in (502, 503, 504):
            return True, "UNAVAILABLE"
        # 4xx other than 429 (bad request, auth, permission, not found) is a
        # permanent misconfiguration -- retrying it would never succeed.
        return False, None
    return True, None


def _make_openai_provider(api_key, model, question):
    if not api_key:
        return provider_manager.Provider(name="openai", configured=False, call=None)

    client = _build_openai_client(api_key)

    def _call():
        try:
            return _run_openai_conversation(client, model, question)
        except Exception as exc:
            retryable, reason = _classify_openai_error(exc)
            logger.warning("Ask RSE Market: openai call failed (retryable=%s): %s", retryable, exc)
            raise provider_manager.ProviderFailure(str(exc), retryable=retryable, reason=reason) from exc

    return provider_manager.Provider(name="openai", configured=True, call=_call)


def _generic_error_message(reason):
    if reason == "RESOURCE_EXHAUSTED":
        return ("Ask RSE Market has reached its current request limit with the AI "
                "provider. Please try again in a few minutes.")
    if reason == "UNAVAILABLE":
        return "The AI provider is experiencing high demand right now. Please try again in a moment."
    return "The assistant is temporarily unavailable. Please try again shortly."


def answer_question(question: str) -> dict:
    """Returns {"configured": bool, "answer": str, "sources": [...], "used_tools": [...]}.
    Never raises -- any failure is turned into a safe, generic message.

    Tries Gemini (primary), then an optional second Gemini configuration
    (backup project/key), then OpenAI, in that order -- see
    app/services/ai_provider_manager.py for the retry/failover mechanics.
    Provider switching is invisible to the caller: no error text, provider
    name, or internal detail from a failed provider ever reaches the
    response. Every provider answers using the exact same RSE tool-calling
    loop against app/services/rse_query_tools.py; only the model making the
    call changes, and a valid RSE result (including "data unavailable")
    never triggers failover to another provider.
    """
    cfg = current_app.config

    try:
        providers = [
            _make_gemini_provider(
                "gemini-primary", cfg.get("GEMINI_API_KEY"),
                cfg.get("GEMINI_MODEL", "gemini-flash-latest"), question,
            ),
            _make_gemini_provider(
                "gemini-backup", cfg.get("GEMINI_API_KEY_BACKUP"),
                cfg.get("GEMINI_MODEL_BACKUP") or cfg.get("GEMINI_MODEL", "gemini-flash-latest"), question,
            ),
            _make_openai_provider(
                cfg.get("OPENAI_API_KEY"), cfg.get("OPENAI_MODEL", "gpt-4o-mini"), question,
            ),
        ]
        result = provider_manager.answer_with_failover(providers)
        return {"configured": True, **result}
    except provider_manager.NoProviderConfigured:
        return {
            "configured": False,
            "answer": "Ask RSE Market isn't configured yet. An administrator needs to set "
                      "an AI provider API key before this assistant can answer questions.",
            "sources": [],
            "used_tools": [],
        }
    except provider_manager.AllProvidersFailed as exc:
        reason = getattr(exc.last_failure, "reason", None)
        logger.error("Ask RSE Market: all configured providers failed (last reason=%s)", reason)
        return {
            "configured": True,
            "answer": _generic_error_message(reason),
            "sources": [],
            "used_tools": [],
            "error": True,
        }
    except Exception:
        # Last-resort safety net -- answer_question() must never raise.
        logger.exception("Ask RSE Market assistant call failed unexpectedly")
        return {
            "configured": True,
            "answer": _generic_error_message(None),
            "sources": [],
            "used_tools": [],
            "error": True,
        }
