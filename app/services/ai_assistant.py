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
"""

import json
import logging

from flask import current_app
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.services import rse_query_tools as tools

logger = logging.getLogger("rse_intelligence.assistant")

MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """You are "Ask RSE Market", a market-data assistant for the RSE \
Intelligence platform (Rwanda Stock Exchange). You help Administrator and Analyst \
users understand the platform's own verified market data.

Rules you must follow at all times:
1. You have NO market knowledge of your own. Never state a price, volume, index \
value, exchange rate, bond figure, or any other RSE market fact unless it came \
from a tool call you just made in this conversation. If you have not called a \
tool for a fact, you do not know it.
2. If a tool result says a value was not found or is missing, say so plainly \
("no verified data is available for X") — never guess, estimate, or fill in a \
plausible-sounding number, and never treat a missing value as zero.
3. Always state which report date the figures came from, exactly as given by \
the tool result. Never imply older data is "the latest" — if the most recent \
report is not yet verified, say so explicitly.
4. Clearly separate observed data (what the report states), calculated values \
(differences, rankings — always computed by the tools, never by you), and your \
own brief analysis/explanation.
5. Do not give investment advice, buy/sell recommendations, or personalized \
financial guidance. You may describe what the data shows; you must not tell the \
user what to do about it.
6. If the question is not about RSE market data on this platform, briefly say \
that you can only help with verified RSE market data and suggest what you can \
answer instead.
7. Keep answers concise, factual, and professional — this is an institutional \
market-intelligence tool, not a casual chatbot.
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


def _get_client():
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


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


def answer_question(question: str) -> dict:
    """Returns {"configured": bool, "answer": str, "sources": [...], "used_tools": [...]}.
    Never raises -- any failure is turned into a safe, generic message."""
    client = _get_client()
    if client is None:
        return {
            "configured": False,
            "answer": "Ask RSE Market isn't configured yet. An administrator needs to set "
                      "a Gemini API key before this assistant can answer questions.",
            "sources": [],
            "used_tools": [],
        }

    model = current_app.config.get("GEMINI_MODEL", "gemini-2.5-flash")
    config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=GEMINI_TOOLS,
        temperature=0.2,
    )
    contents = [genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=question)])]
    sources = []
    used_tools = []

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            response = client.models.generate_content(model=model, contents=contents, config=config)
            function_calls = response.function_calls

            if not function_calls:
                return {
                    "configured": True,
                    "answer": response.text or "I couldn't generate a response for that question.",
                    "sources": _dedupe_sources(sources),
                    "used_tools": used_tools,
                }

            contents.append(response.candidates[0].content)

            response_parts = []
            for call in function_calls:
                name = call.name
                args = call.args or {}

                func = tools.TOOL_FUNCTIONS.get(name)
                if func is None:
                    result = {"found": False, "message": "That capability is not available."}
                else:
                    try:
                        result = func(**args)
                    except TypeError:
                        # The model passed arguments the tool doesn't accept -- fail closed
                        # with an explicit "not found" rather than letting an exception
                        # about internal argument shapes reach the user.
                        result = {"found": False, "message": "That question could not be understood well enough to look up."}
                    used_tools.append(name)
                    sources.extend(_extract_sources(name, result))

                # Normalize to plain JSON-safe types (e.g. date objects -> strings)
                # before handing the result back to the model.
                safe_result = json.loads(json.dumps(result, default=str))
                response_parts.append(genai_types.Part.from_function_response(name=name, response=safe_result))

            contents.append(genai_types.Content(role="user", parts=response_parts))

        return {
            "configured": True,
            "answer": "I wasn't able to finish answering that question. Please try rephrasing it, "
                      "or ask about one thing at a time.",
            "sources": _dedupe_sources(sources),
            "used_tools": used_tools,
        }
    except genai_errors.APIError as exc:
        logger.exception("Ask RSE Market assistant call failed (Gemini API error %s, status=%s)", exc.code, exc.status)
        return {
            "configured": True,
            "answer": "The assistant is temporarily unavailable. Please try again shortly.",
            "sources": [],
            "used_tools": [],
            "error": True,
        }
    except Exception:
        logger.exception("Ask RSE Market assistant call failed")
        return {
            "configured": True,
            "answer": "The assistant is temporarily unavailable. Please try again shortly.",
            "sources": [],
            "used_tools": [],
            "error": True,
        }
