import os

from flask import Flask, render_template

from config import config_by_name


def create_app(env_name: str = None):
    env_name = env_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name.get(env_name, config_by_name["development"]))

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, "..", "instance"), exist_ok=True)

    _register_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_cli(app)

    return app


def _register_extensions(app):
    from app.extensions import csrf, db, login_manager, migrate

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))


def _register_blueprints(app):
    from app.api import register_api_blueprints
    from app.auth.routes import auth_bp
    from app.views.admin import admin_bp
    from app.views.assistant import assistant_bp
    from app.views.bonds import bonds_bp
    from app.views.dashboard import dashboard_bp
    from app.views.equities import equities_bp
    from app.views.market import market_bp
    from app.views.reports import reports_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(equities_bp, url_prefix="/equities")
    app.register_blueprint(bonds_bp, url_prefix="/bonds")
    app.register_blueprint(market_bp, url_prefix="/market")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(assistant_bp, url_prefix="/assistant")

    register_api_blueprints(app)


def _register_error_handlers(app):
    from app.services.errors import register_error_handlers

    register_error_handlers(app)


def _register_cli(app):
    from app.services.cli import register_cli_commands

    register_cli_commands(app)
