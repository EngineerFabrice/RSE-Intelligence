import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'instance' / 'rse_intelligence.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "instance" / "uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "25")) * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = {"pdf"}

    TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "") or None

    # "Ask RSE Market" assistant (spec: Phase 4). Left unset in a fresh checkout --
    # the assistant reports itself as "not configured" rather than failing, see
    # app/services/ai_assistant.py. Provider priority/failover mechanics live in
    # app/services/ai_provider_manager.py: Gemini (primary) -> Gemini (backup,
    # optional) -> OpenAI (final fallback) -> safe generic error.
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or None
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

    # Optional second Gemini configuration used only if the primary fails. This
    # must be a separately configured Gemini project/key, not just a second key
    # in the same project -- two keys in one project share the same quota and
    # would fail together. Leave blank to skip the backup tier entirely.
    GEMINI_API_KEY_BACKUP = os.environ.get("GEMINI_API_KEY_BACKUP", "") or None
    GEMINI_MODEL_BACKUP = os.environ.get("GEMINI_MODEL_BACKUP", "") or GEMINI_MODEL

    # Final fallback provider if both Gemini tiers fail. Leave blank to skip it.
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "") or None
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Roles recognised by the platform (spec §33)
    ROLES = ["administrator", "analyst", "reviewer", "viewer"]


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    UPLOAD_FOLDER = str(BASE_DIR / "instance" / "test_uploads")


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
