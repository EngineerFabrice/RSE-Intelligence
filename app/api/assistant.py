from flask import Blueprint, request
from flask_login import login_required

from app.api.utils import error, ok
from app.auth.decorators import roles_required
from app.services.ai_assistant import answer_question
from app.services.audit import log_action

assistant_api_bp = Blueprint("assistant_api", __name__)

MAX_QUESTION_LENGTH = 500


@assistant_api_bp.route("/ask", methods=["POST"])
@login_required
@roles_required("administrator", "analyst")
def ask():
    """"Ask RSE Market" (spec: Phase 4) -- Administrator/Analyst only (enforced by
    roles_required above, not just hidden in the UI). The question never reaches the
    database directly: it goes to the AI layer, which can only retrieve facts through
    the controlled tool functions in app/services/rse_query_tools.py."""
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()

    if not question:
        return error("Please enter a question.", "missing_question")
    if len(question) > MAX_QUESTION_LENGTH:
        return error(f"Please keep questions under {MAX_QUESTION_LENGTH} characters.", "question_too_long")

    result = answer_question(question)

    log_action("ai_query", entity_type="assistant", description=question[:200])

    return ok(result)
