import logging
import os
from urllib.parse import unquote

from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required

from models import db, Textbook

logger = logging.getLogger(__name__)

bp = Blueprint("textbooks", __name__, url_prefix="/api")


@bp.route("/files/textbooks/<path:filename>", methods=["GET"])
def serve_textbook(filename):
    try:
        decoded_filename = unquote(filename)
        logger.info("Serving textbook file: %s", decoded_filename)

        textbook_folder = current_app.config["TEXTBOOK_FOLDER"]
        file_path = os.path.join(textbook_folder, decoded_filename)

        if not os.path.exists(file_path):
            return jsonify({"error": f"文件不存在: {decoded_filename}"}), 404

        real_path = os.path.abspath(file_path)
        real_folder = os.path.abspath(textbook_folder)
        if not real_path.startswith(real_folder):
            return jsonify({"error": "无权访问该文件"}), 403

        mime_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".md": "text/markdown",
        }
        _, ext = os.path.splitext(file_path)
        mime_type = mime_types.get(ext.lower(), "application/octet-stream")

        return send_file(file_path, mimetype=mime_type)
    except Exception as e:
        logger.error("Textbook file serve error: %s", e, exc_info=True)
        return jsonify({"error": f"文件访问失败: {str(e)}"}), 500


@bp.route("/textbooks", methods=["GET"])
def get_textbooks():
    category = request.args.get("category")
    query = Textbook.query
    if category:
        query = query.filter_by(category=category)
    textbooks = query.all()
    return jsonify([t.to_dict() for t in textbooks]), 200


@bp.route("/textbooks/<int:textbook_id>", methods=["GET"])
def get_textbook(textbook_id):
    textbook = Textbook.query.get(textbook_id)
    if not textbook:
        return jsonify({"error": "课本不存在"}), 404
    return jsonify(textbook.to_dict()), 200


@bp.route("/textbooks", methods=["POST"])
@jwt_required()
def create_textbook():
    data = request.get_json()
    if not data or not data.get("title") or not data.get("content"):
        return jsonify({"error": "缺少必要的字段"}), 400

    textbook = Textbook(
        title=data["title"],
        description=data.get("description"),
        category=data.get("category", "uncategorized"),
        content=data["content"],
    )
    db.session.add(textbook)
    db.session.commit()
    return jsonify(textbook.to_dict()), 201
