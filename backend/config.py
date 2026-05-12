import os
from datetime import timedelta


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///elearning.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-change-this")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=30)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=90)
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    TEXTBOOK_FOLDER = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
