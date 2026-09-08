import logging

from flask import jsonify, render_template, request

logger = logging.getLogger("rse_intelligence")


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify(status="error", code="not_found", message="The requested resource was not found."), 404
        return render_template("errors/generic.html", title="Page Not Found",
                                message="The page you're looking for doesn't exist or may have moved."), 404

    @app.errorhandler(403)
    def forbidden(e):
        if _wants_json():
            return jsonify(status="error", code="forbidden", message="You do not have permission to do that."), 403
        return render_template("errors/generic.html", title="Access Denied",
                                message="You don't have permission to view this page."), 403

    @app.errorhandler(413)
    def too_large(e):
        if _wants_json():
            return jsonify(status="error", code="file_too_large", message="The uploaded file exceeds the size limit."), 413
        return render_template("errors/generic.html", title="File Too Large",
                                message="The uploaded file exceeds the maximum allowed size."), 413

    @app.errorhandler(400)
    def bad_request(e):
        if _wants_json():
            return jsonify(status="error", code="bad_request", message=str(e.description or "Invalid request.")), 400
        return render_template("errors/generic.html", title="Invalid Request",
                                message=str(e.description or "Invalid request.")), 400

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Unhandled server error")
        if _wants_json():
            return jsonify(status="error", code="server_error",
                            message="Something went wrong while processing your request. No data was changed."), 500
        return render_template("errors/generic.html", title="Something Went Wrong",
                                message="We couldn't complete this action. No market data was changed. "
                                        "Please try again or contact an administrator."), 500
