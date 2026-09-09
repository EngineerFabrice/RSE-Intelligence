"""Tests for "Ask RSE Market" (spec: Phase 4).

Covers the RBAC matrix (Administrator/Analyst only), the query-tool layer
(app/services/rse_query_tools.py) directly -- real data, no fabricated
values, correct historical dates, correct calculations, source/verification
metadata -- and the API endpoint's handling of the AI layer, always with the
Gemini client replaced by a scripted fake so tests never make a real network
call regardless of what GEMINI_API_KEY happens to be set to in the
environment.
"""

from datetime import date

from google.genai import errors as genai_errors
from google.genai import types as genai_types

from tests.fixtures.sample_report import build_sample_pdf

from app.extensions import db
from app.ingestion.pipeline import process_report
from app.models.audit_log import AuditLog
from app.models.report import Report
from app.services import duplicate_detection, rse_query_tools as tools
from app.services.ai_assistant import answer_question


def _seed_approved_report(app, tmp_path, name="sample.pdf", report_date=None):
    pdf_path = tmp_path / name
    build_sample_pdf(pdf_path, shares_traded_mismatch=False)
    file_bytes = pdf_path.read_bytes()

    report = Report(filename=name, original_filename=name,
                     file_hash=duplicate_detection.compute_file_hash(file_bytes), storage_path=str(pdf_path))
    db.session.add(report)
    db.session.commit()
    process_report(report.id)
    db.session.refresh(report)

    report.approval_status = "approved"
    report.processing_status = "approved"
    if report_date is not None:
        report.report_date = report_date
    db.session.commit()
    db.session.refresh(report)
    return report


# ---------------------------------------------------------------------------
# Fake Gemini client -- scripted responses, no network access whatsoever.

def _fake_response(text=None, function_calls=None):
    """Builds a real google.genai GenerateContentResponse (so response.text /
    response.function_calls behave exactly as they would for a real call),
    from a plain text answer and/or a list of (name, args) function calls."""
    parts = []
    if function_calls:
        parts.extend(genai_types.Part.from_function_call(name=name, args=args) for name, args in function_calls)
    if text is not None:
        parts.append(genai_types.Part.from_text(text=text))
    return genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=genai_types.Content(role="model", parts=parts))]
    )


class _FakeModels:
    def __init__(self, script):
        self._script = list(script)
        self.received_contents = []

    def generate_content(self, *, model, contents, config):
        self.received_contents.append(contents)
        if not self._script:
            raise AssertionError("Fake Gemini script ran out of scripted responses.")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class _FakeClient:
    def __init__(self, script):
        self.models = _FakeModels(script)


def _fake_genai_client_factory(script):
    """A drop-in replacement for genai.Client(api_key=...) that replays `script`."""
    def _factory(api_key=None, **kwargs):
        return _FakeClient(script)
    return _factory


def _install_fake_gemini(app, monkeypatch, script, api_key="test-key"):
    app.config["GEMINI_API_KEY"] = api_key
    monkeypatch.setattr("app.services.ai_assistant.genai.Client", _fake_genai_client_factory(script))


# ---------------------------------------------------------------------------
# 1-5: RBAC matrix

def test_admin_can_access_assistant_page(admin_client):
    resp = admin_client.get("/assistant/")
    assert resp.status_code == 200
    assert "Ask RSE Market" in resp.get_data(as_text=True)


def test_analyst_can_access_assistant_page(analyst_client):
    resp = analyst_client.get("/assistant/")
    assert resp.status_code == 200
    assert "Ask RSE Market" in resp.get_data(as_text=True)


def test_viewer_cannot_access_assistant_page(viewer_client):
    assert viewer_client.get("/assistant/").status_code == 403
    resp = viewer_client.post("/api/assistant/ask", json={"question": "test"})
    assert resp.status_code == 403


def test_reviewer_cannot_access_assistant_page(reviewer_client):
    assert reviewer_client.get("/assistant/").status_code == 403
    resp = reviewer_client.post("/api/assistant/ask", json={"question": "test"})
    assert resp.status_code == 403


def test_unauthenticated_cannot_access_assistant_page(client):
    resp = client.get("/assistant/")
    assert resp.status_code in (302, 401, 403)
    if resp.status_code == 302:
        assert "/auth/login" in resp.headers["Location"]

    api_resp = client.post("/api/assistant/ask", json={"question": "test"})
    assert api_resp.status_code == 401


def test_floating_launcher_is_the_only_entry_point_for_admin(admin_client):
    html = admin_client.get("/").get_data(as_text=True)
    assert "Ask RSE Market" in html
    assert 'class="assistant-launcher"' in html
    # Exactly one entry point -- no separate top nav tab/link duplicating it.
    assert html.count('href="/assistant/"') == 1


def test_floating_launcher_hidden_for_viewer(viewer_client):
    html = viewer_client.get("/").get_data(as_text=True)
    assert "Ask RSE Market" not in html
    assert "assistant-launcher" not in html


def test_floating_launcher_hidden_for_reviewer(reviewer_client):
    html = reviewer_client.get("/").get_data(as_text=True)
    assert "Ask RSE Market" not in html
    assert "assistant-launcher" not in html


# ---------------------------------------------------------------------------
# 6-10: the query-tool layer itself -- real data, no hallucination, correct
# dates, correct calculations, source/verification metadata. No Gemini
# involved at all; these test the deterministic backend directly.

def test_get_equity_returns_real_verified_data(app, tmp_path):
    _seed_approved_report(app, tmp_path)
    result = tools.get_equity("BLR")

    assert result["found"] is True
    assert result["equity"]["closing_price"] == 515.0
    assert result["equity"]["previous_close"] == 500.0
    assert result["equity"]["volume"] == 100
    assert result["report"]["verified"] is True
    assert result["report"]["report_date"] == "2026-09-07"


def test_missing_equity_is_not_hallucinated(app, tmp_path):
    _seed_approved_report(app, tmp_path)

    result = tools.get_equity("NOSUCHTICKER")
    assert result["found"] is False
    assert "equity" not in result
    assert "NOSUCHTICKER" in result["message"]


def test_missing_field_stays_none_not_zero(app, tmp_path):
    # The fixture PDF's equity table has no "today's high/low" columns, so the
    # parser correctly leaves these fields unset -- the tool must surface that
    # as None, never coerce it to 0.
    _seed_approved_report(app, tmp_path)
    result = tools.get_equity("BOK")
    assert result["equity"]["today_high"] is None
    assert result["equity"]["today_low"] is None


def test_equity_history_uses_correct_report_dates(app, tmp_path):
    older = _seed_approved_report(app, tmp_path, name="a.pdf", report_date=date(2026, 9, 1))
    newer = _seed_approved_report(app, tmp_path, name="b.pdf", report_date=date(2026, 9, 8))
    assert older.id != newer.id

    result = tools.get_equity_history("BOK", limit=10)
    assert result["found"] is True
    dates = [h["report_date"] for h in result["history"]]
    assert dates == sorted(dates)  # oldest to newest
    assert dates[0] == "2026-09-01"
    assert dates[-1] == "2026-09-08"


def test_top_performers_and_comparison_calculations_are_correct(app, tmp_path):
    _seed_approved_report(app, tmp_path)

    ranking = tools.top_performers(metric="volume", limit=5)
    assert ranking["found"] is True
    assert ranking["ranking"][0]["symbol"] == "BOK"  # 21,600 shares > BLR's 100
    assert ranking["ranking"][0]["volume"] == 21600

    comparison = tools.compare_equities(["BOK", "BLR"])
    assert comparison["found"] is True
    diff = comparison["comparison"]
    assert diff["closing_price_difference"] == 145.0  # 660 - 515
    assert diff["volume_difference"] == 21500  # 21600 - 100


def test_source_and_verification_metadata_present(app, tmp_path):
    _seed_approved_report(app, tmp_path)
    result = tools.get_market_overview()

    assert result["found"] is True
    assert result["report"]["report_id"] is not None
    assert result["report"]["report_date"] == "2026-09-07"
    assert result["report"]["verified"] is True
    assert result["report"]["status"] == "Verified"


def test_latest_report_status_distinguishes_unverified_from_verified(app, tmp_path):
    verified = _seed_approved_report(app, tmp_path, name="verified.pdf", report_date=date(2026, 9, 1))

    # A second, later report that has NOT been approved.
    pdf_path = tmp_path / "pending.pdf"
    build_sample_pdf(pdf_path, shares_traded_mismatch=False)
    unverified = Report(filename="pending.pdf", original_filename="pending.pdf",
                         file_hash=duplicate_detection.compute_file_hash(pdf_path.read_bytes()),
                         storage_path=str(pdf_path))
    db.session.add(unverified)
    db.session.commit()
    process_report(unverified.id)
    db.session.refresh(unverified)
    unverified.report_date = date(2026, 9, 8)
    db.session.commit()

    status = tools.get_latest_report_status()
    assert status["found"] is True
    assert status["most_recent_report"]["report_id"] == unverified.id
    assert status["most_recent_report"]["verified"] is False
    assert status["latest_verified_report"]["report_id"] == verified.id
    assert status["latest_is_verified"] is False


def test_no_verified_data_available_is_stated_clearly(app):
    # No report has been uploaded/approved at all.
    result = tools.get_equity("BOK")
    assert result["found"] is False
    assert "message" in result

    overview = tools.get_market_overview()
    assert overview["found"] is False
    assert "message" in overview


# ---------------------------------------------------------------------------
# 11: Gemini/API failures are handled safely; the assistant is never
# "unconfigured" silently, and never leaks internal error detail.

def test_assistant_not_configured_returns_clear_message(app):
    app.config["GEMINI_API_KEY"] = None
    result = answer_question("What was the latest market activity?")
    assert result["configured"] is False
    assert "configured" in result["answer"].lower()
    assert result["sources"] == []


def test_assistant_handles_gemini_failure_gracefully(app, monkeypatch):
    _install_fake_gemini(app, monkeypatch, script=[RuntimeError("simulated network failure")])

    result = answer_question("What was the latest market activity?")
    assert result["configured"] is True
    assert result.get("error") is True
    assert "temporarily unavailable" in result["answer"].lower()
    # No internal exception text/traceback leaks into the user-facing answer.
    assert "RuntimeError" not in result["answer"]
    assert "simulated network failure" not in result["answer"]


def test_ask_endpoint_handles_gemini_failure_without_500(admin_client, app, monkeypatch):
    _install_fake_gemini(app, monkeypatch, script=[RuntimeError("boom")])

    resp = admin_client.post("/api/assistant/ask", json={"question": "What was the latest market activity?"})
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["error"] is True
    assert "boom" not in body["answer"]


def test_ask_endpoint_rejects_empty_and_oversized_questions(admin_client):
    assert admin_client.post("/api/assistant/ask", json={"question": ""}).status_code == 400
    assert admin_client.post("/api/assistant/ask", json={"question": "x" * 501}).status_code == 400


def test_gemini_quota_exhaustion_is_handled_like_any_other_api_failure(app, monkeypatch):
    # Regression test for the production incident where the configured provider key had
    # no quota left (originally OpenAI's insufficient_quota/credit_balance_exhausted;
    # now modeled on Gemini's equivalent 429 RESOURCE_EXHAUSTED). answer_question()
    # catches genai_errors.APIError (and any other exception) without discriminating
    # further -- this exercises exactly the handling path a real quota error takes,
    # and confirms the failure is caught at the Gemini call itself, before any
    # tool/database access, and never surfaces quota/internal detail to the user.
    quota_error = genai_errors.ClientError(
        429,
        {"error": {"message": "You exceeded your current quota, please check your plan and billing details.",
                    "status": "RESOURCE_EXHAUSTED"}},
    )
    _install_fake_gemini(app, monkeypatch, script=[quota_error])

    result = answer_question("Which equity had the highest trading volume?")
    assert result["configured"] is True
    assert result["error"] is True
    assert result["used_tools"] == []  # never reached tool-calling or the database
    assert "RESOURCE_EXHAUSTED" not in result["answer"]
    assert "quota" not in result["answer"].lower()
    assert "429" not in result["answer"]


# ---------------------------------------------------------------------------
# Full round-trip through the API with a scripted tool call -- confirms the
# endpoint actually executes the real backend tool against real seeded data
# (not anything the fake model invents) and returns it with source metadata.

def test_ask_endpoint_executes_real_tool_and_returns_sources(admin_client, app, tmp_path, monkeypatch):
    report = _seed_approved_report(app, tmp_path)

    script = [
        _fake_response(function_calls=[("get_equity", {"symbol": "BLR"})]),
        _fake_response(text="BLR closed at 515.00, up from a previous close of 500.00, "
                             "as of the 2026-09-07 verified report."),
    ]
    _install_fake_gemini(app, monkeypatch, script)

    resp = admin_client.post("/api/assistant/ask", json={"question": "What was BLR's closing price?"})
    assert resp.status_code == 200
    body = resp.get_json()["data"]

    assert body["configured"] is True
    assert "515" in body["answer"]
    assert body["used_tools"] == ["get_equity"]
    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert source["report_id"] == report.id
    assert source["report_date"] == "2026-09-07"
    assert source["verified"] is True
    assert source["section"] == "Equities"

    # The AI query was audit-logged, consistent with the rest of the platform.
    entry = AuditLog.query.filter_by(action="ai_query").order_by(AuditLog.id.desc()).first()
    assert entry is not None
    assert "BLR" in entry.description


def test_analyst_can_successfully_ask_a_question(analyst_client, app, tmp_path, monkeypatch):
    _seed_approved_report(app, tmp_path)
    script = [_fake_response(text="No tool needed for this greeting.")]
    _install_fake_gemini(app, monkeypatch, script)

    resp = analyst_client.post("/api/assistant/ask", json={"question": "hello"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["configured"] is True
