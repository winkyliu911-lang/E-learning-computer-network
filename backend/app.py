import logging
import os

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import text

from config import Config
from models import db
from services.logging_config import setup_logging
from services.llm_service import init_llm_client

setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Extensions
db.init_app(app)
CORS(app, origins=os.environ.get("CORS_ORIGINS", "*").split(","))
jwt = JWTManager(app)

# LLM client
init_llm_client()

# JWT callbacks
@jwt.user_identity_loader
def user_identity_lookup(identity):
    return str(identity)


@jwt.unauthorized_loader
def jwt_unauthorized_callback(reason):
    logger.warning("JWT unauthorized: %s", reason)
    return jsonify({"error": "Authorization header missing or malformed", "msg": reason}), 401


@jwt.invalid_token_loader
def jwt_invalid_token_callback(reason):
    logger.warning("JWT invalid token: %s", reason)
    return jsonify({"error": "Invalid token", "msg": reason}), 422


@jwt.expired_token_loader
def jwt_expired_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Token expired"}), 401


# Register blueprints
from routes.auth import bp as auth_bp
from routes.videos import bp as videos_bp
from routes.textbooks import bp as textbooks_bp
from routes.chat import bp as chat_bp
from routes.exercises import bp as exercises_bp
from routes.rag import bp as rag_bp
from routes.notes import bp as notes_bp

app.register_blueprint(auth_bp)
app.register_blueprint(videos_bp)
app.register_blueprint(textbooks_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(exercises_bp)
app.register_blueprint(rag_bp)
app.register_blueprint(notes_bp)

# DB migration
with app.app_context():
    try:
        db.create_all()
        table_columns = db.session.execute(text("PRAGMA table_info(chats)")).fetchall()
        column_names = [row[1] for row in table_columns]
        if "session_id" not in column_names:
            db.session.execute(text("ALTER TABLE chats ADD COLUMN session_id VARCHAR(64)"))
            db.session.commit()
            logger.info("Migration: added session_id to chats")
        if "conversation_json" not in column_names:
            db.session.execute(text("ALTER TABLE chats ADD COLUMN conversation_json TEXT"))
            db.session.commit()
            logger.info("Migration: added conversation_json to chats")
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database initialization failed: %s", e)


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "资源不存在"}), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({"error": "服务器内部错误"}), 500


# Dev seeding endpoint
@app.route("/api/init-db", methods=["POST"])
def init_db():
    with app.app_context():
        try:
            from seed_data import seed_courses, seed_textbooks

            db.create_all()
            seed_courses(db)
            seed_textbooks(db)
            return jsonify({"message": "数据库初始化成功"}), 200
        except Exception as e:
            db.session.rollback()
            logger.error("DB init failed: %s", e, exc_info=True)
            return jsonify({"error": f"初始化失败: {str(e)}"}), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        try:
            from seed_data import seed_courses, seed_textbooks

            seed_courses(db)
            seed_textbooks(db)
        except Exception as e:
            logger.error("Startup seeding failed: %s", e, exc_info=True)

        # Auto-init RAG from Data/ knowledge base
        from pathlib import Path

        documents_dir = Path(__file__).parent.parent / "Data"
        if documents_dir.exists():
            file_paths = (
                list(documents_dir.glob("*.pdf"))
                + list(documents_dir.glob("*.docx"))
                + list(documents_dir.glob("*.md"))
            )
            if file_paths:
                try:
                    from rag_manager import get_rag_manager

                    rag_manager = get_rag_manager()
                    results = rag_manager.add_documents(
                        [str(p) for p in file_paths], document_source="builtin"
                    )
                    logger.info(
                        "RAG initialized: %d files, %d chunks",
                        results["processed_files"],
                        results["total_chunks"],
                    )
                except Exception as e:
                    logger.error("RAG init failed: %s", e, exc_info=True)

    app.run(debug=True, host="0.0.0.0", port=8000)
