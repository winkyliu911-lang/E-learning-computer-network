import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, Note

logger = logging.getLogger(__name__)

bp = Blueprint("notes", __name__, url_prefix="/api")


@bp.route("/notes", methods=["POST"])
@jwt_required()
def create_note():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        if not data or not data.get("title") or not data.get("content"):
            return jsonify({"error": "标题和内容不能为空"}), 400

        note = Note(
            user_id=user_id,
            textbook_title=data.get("textbook_title", ""),
            title=data["title"],
            content=data["content"],
            page_number=data.get("page_number"),
        )
        db.session.add(note)
        db.session.commit()
        return jsonify(note.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/notes", methods=["GET"])
@jwt_required()
def get_notes():
    try:
        user_id = int(get_jwt_identity())
        query = Note.query.filter_by(user_id=user_id)

        textbook = request.args.get("textbook_title")
        if textbook:
            query = query.filter_by(textbook_title=textbook)
        keyword = request.args.get("keyword")
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(db.or_(Note.title.like(like), Note.content.like(like)))

        notes = query.order_by(Note.created_at.desc()).all()
        return jsonify([n.to_dict() for n in notes]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/notes/<int:note_id>", methods=["PUT"])
@jwt_required()
def update_note(note_id):
    try:
        user_id = int(get_jwt_identity())
        note = Note.query.filter_by(id=note_id, user_id=user_id).first()
        if not note:
            return jsonify({"error": "笔记不存在"}), 404

        data = request.get_json()
        if data.get("title"):
            note.title = data["title"]
        if data.get("content"):
            note.content = data["content"]
        if "page_number" in data:
            note.page_number = data["page_number"]

        db.session.commit()
        return jsonify(note.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/notes/<int:note_id>", methods=["DELETE"])
@jwt_required()
def delete_note(note_id):
    try:
        user_id = int(get_jwt_identity())
        note = Note.query.filter_by(id=note_id, user_id=user_id).first()
        if not note:
            return jsonify({"error": "笔记不存在"}), 404

        db.session.delete(note)
        db.session.commit()
        return jsonify({"message": "已删除"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
