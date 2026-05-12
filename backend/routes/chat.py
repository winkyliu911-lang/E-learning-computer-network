import base64
import datetime
import json
import logging
import os
import uuid

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from models import db, Chat
from services.llm_service import call_qwen_api, trim_text, MAX_HISTORY_MESSAGE_CHARS
from rag_manager import get_rag_manager
from file_extractor import convert_upload_to_images

logger = logging.getLogger(__name__)

bp = Blueprint("chat", __name__, url_prefix="/api")

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _extract_image_data_url(file_path):
    try:
        ext_to_mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
        }
        ext = os.path.splitext(file_path)[1].lower()
        mime_type = ext_to_mime.get(ext)
        if not mime_type:
            return None
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"
    except Exception as e:
        logger.warning("Image data URL conversion failed: %s", e)
        return None


def _parse_stored_file_paths(file_path_value):
    if not file_path_value:
        return []
    return [p for p in file_path_value.split("||") if p]


def _build_history_messages(history_items):
    messages = []
    if not isinstance(history_items, list):
        return messages
    for item in history_items:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        text = trim_text(item.get("content"), MAX_HISTORY_MESSAGE_CHARS)
        if not text or text.startswith("❌"):
            continue
        messages.append({"role": role, "content": [{"type": "text", "text": text}]})
    return messages


def _build_session_history_messages(user_id, session_id):
    messages = []
    history_image_count = 0
    if not session_id:
        return messages, history_image_count

    try:
        records = Chat.query.filter_by(user_id=user_id, session_id=session_id).order_by(Chat.created_at.asc()).all()
    except Exception as e:
        logger.warning("Failed to load session history: %s", e)
        return messages, history_image_count

    for record in records:
        if not record.conversation_json:
            continue
        try:
            conversation_items = json.loads(record.conversation_json)
        except Exception:
            conversation_items = []

        if isinstance(conversation_items, list) and conversation_items:
            for item in conversation_items:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                if role not in ("user", "assistant"):
                    continue
                text_content = trim_text(item.get("content"), MAX_HISTORY_MESSAGE_CHARS)
                if not text_content:
                    continue
                if role == "user":
                    user_content = [{"type": "text", "text": text_content}]
                    for stored_path in item.get("file_paths") or []:
                        data_url = _extract_image_data_url(stored_path)
                        if data_url:
                            user_content.append({"type": "image_url", "image_url": {"url": data_url}})
                            history_image_count += 1
                    messages.append({"role": "user", "content": user_content})
                else:
                    if text_content.startswith("❌"):
                        continue
                    messages.append({"role": "assistant", "content": [{"type": "text", "text": text_content}]})
            return messages, history_image_count

    for record in records:
        question_text = trim_text(record.question, MAX_HISTORY_MESSAGE_CHARS)
        answer_text = trim_text(record.answer, MAX_HISTORY_MESSAGE_CHARS)
        if not question_text:
            continue
        user_content = [{"type": "text", "text": question_text}]
        for stored_path in _parse_stored_file_paths(record.file_path):
            data_url = _extract_image_data_url(stored_path)
            if data_url:
                user_content.append({"type": "image_url", "image_url": {"url": data_url}})
                history_image_count += 1
        messages.append({"role": "user", "content": user_content})
        if answer_text and not answer_text.startswith("❌"):
            messages.append({"role": "assistant", "content": [{"type": "text", "text": answer_text}]})

    return messages, history_image_count


@bp.route("/chat", methods=["POST"])
@jwt_required()
def chat():
    data = request.get_json(silent=True)
    file_paths = []
    rag_context = ""
    image_data_urls = []

    if not data:
        form = request.form
        if form and form.get("question"):
            data = {
                "question": form.get("question"),
                "context": form.get("context", ""),
                "use_rag": form.get("use_rag", "true").lower() == "true",
                "session_id": form.get("session_id", ""),
                "history_messages": form.get("history_messages", "[]"),
            }
        else:
            return jsonify({"error": "请求体必须为 JSON 或 form-data，并包含字段 question"}), 400

    user_id_raw = get_jwt_identity()
    try:
        user_id = int(user_id_raw)
    except Exception:
        user_id = user_id_raw

    question = (data.get("question") or "").strip()
    context = (data.get("context") or "").strip()
    use_rag = data.get("use_rag", True)
    session_id = (data.get("session_id") or "").strip()
    history_messages_raw = data.get("history_messages", [])

    if not session_id:
        session_id = str(uuid.uuid4())
    if len(session_id) > 64:
        return jsonify({"error": "session_id 过长，请不超过 64 字符"}), 400

    if isinstance(history_messages_raw, str):
        try:
            history_items = json.loads(history_messages_raw) if history_messages_raw else []
        except Exception:
            history_items = []
    elif isinstance(history_messages_raw, list):
        history_items = history_messages_raw
    else:
        history_items = []

    upload_files = request.files.getlist("files")
    if not upload_files and "file" in request.files:
        upload_files = [request.files["file"]]

    if upload_files:
        allowed_file_ext = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".pdf", ".docx"}
        allowed_mime_prefix = (
            "image/",
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        )

        for index, file in enumerate(upload_files):
            if not file or not file.filename:
                continue
            ext = os.path.splitext(file.filename)[1].lower()
            content_type = (file.mimetype or "").lower()
            if ext not in allowed_file_ext:
                return jsonify({"error": "仅支持上传图片、PDF、DOCX 文件"}), 400

            mime_ok = any(content_type.startswith(prefix) for prefix in allowed_mime_prefix)
            if not mime_ok and ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
                return jsonify({"error": "图片文件类型不正确，请重新上传"}), 400

            filename = f"{user_id}_{int(datetime.datetime.utcnow().timestamp())}_{index}_{secure_filename(file.filename)}"
            current_file_path = os.path.join(UPLOAD_FOLDER, filename)
            try:
                file.save(current_file_path)
                file_paths.append(current_file_path)

                converted_image_paths = convert_upload_to_images(
                    current_file_path, output_dir=UPLOAD_FOLDER, owner_prefix=str(user_id)
                )
                for generated_path in converted_image_paths:
                    data_url = _extract_image_data_url(generated_path)
                    if data_url:
                        image_data_urls.append(data_url)
                        if generated_path not in file_paths:
                            file_paths.append(generated_path)
            except Exception as e:
                logger.error("File save failed: %s", e)

    # 将上传的 PDF/DOCX 文档加入 RAG 知识库，以便检索
    rag_indexed_paths = []
    if upload_files:
        for fp in file_paths:
            ext = os.path.splitext(fp)[1].lower()
            if ext in {".pdf", ".docx"}:
                rag_indexed_paths.append(fp)
        if rag_indexed_paths:
            try:
                rag_manager = get_rag_manager()
                result = rag_manager.add_documents(rag_indexed_paths, document_source="user_upload")
                logger.info("User upload indexed to RAG: %d files, %d chunks", result["processed_files"], result["total_chunks"])
            except Exception as e:
                logger.warning("Failed to index uploaded files to RAG: %s", e)

    if upload_files and not image_data_urls:
        return jsonify({"error": "上传文件处理失败，请检查 PDF/DOCX 内容或重试"}), 400

    if not question:
        return jsonify({"error": "问题不能为空"}), 400
    if len(question) > 2000:
        return jsonify({"error": "问题过长，请不超过 2000 字"}), 400

    try:
        logger.info("Chat request - user_id=%s, question=%.50s, use_rag=%s", user_id, question, use_rag)

        if use_rag:
            try:
                rag_manager = get_rag_manager()
                rag_docs = rag_manager.query(question, top_k=10, score_threshold=0.3)

                if rag_docs:
                    unique_docs = {}
                    for doc in rag_docs:
                        source_file = doc["source"]
                        if source_file not in unique_docs or doc["similarity_score"] > unique_docs[source_file]["similarity_score"]:
                            unique_docs[source_file] = doc

                    unique_docs_list = sorted(unique_docs.values(), key=lambda x: x["similarity_score"], reverse=True)[:3]

                    rag_context = "📚 相关知识库内容:\n"
                    for i, doc in enumerate(unique_docs_list, 1):
                        source = doc["source"]
                        similarity = doc["similarity_score"]
                        logger.info("RAG doc %d: %s (score=%.2f%%)", i, source, similarity * 100)
                        rag_context += f"\n【文档 {i} 来自: {source} (相似度: {similarity:.2%})】\n"
                        rag_context += doc["content"][:300] + "...\n"
                else:
                    logger.info("RAG returned no results")
            except Exception as e:
                logger.warning("RAG retrieval failed: %s", e, exc_info=True)

        combined_context = ""
        if rag_context:
            combined_context = rag_context
        if context:
            combined_context += f"\n\n用户补充信息: {context}"

        history_messages, history_image_count = _build_session_history_messages(user_id, session_id)
        if not history_messages:
            history_messages = _build_history_messages(history_items)
            history_image_count = 0

        answer = call_qwen_api(
            question, context=combined_context,
            image_data_urls=image_data_urls, history_messages=history_messages,
        )

        if answer.startswith("❌"):
            return jsonify({"error": answer}), 500

        session_record = Chat.query.filter_by(user_id=user_id, session_id=session_id).order_by(Chat.created_at.asc()).first()

        new_turns = [
            {"role": "user", "content": question, "file_paths": file_paths},
            {"role": "assistant", "content": answer},
        ]

        if session_record:
            try:
                existing_turns = json.loads(session_record.conversation_json) if session_record.conversation_json else []
                if not isinstance(existing_turns, list):
                    existing_turns = []
            except Exception:
                existing_turns = []
            existing_turns.extend(new_turns)
            session_record.conversation_json = json.dumps(existing_turns, ensure_ascii=False)
            session_record.answer = answer
            old_file_paths = _parse_stored_file_paths(session_record.file_path)
            merged_file_paths = old_file_paths + [p for p in file_paths if p not in old_file_paths]
            session_record.file_path = "||".join(merged_file_paths) if merged_file_paths else None
            chat_record = session_record
        else:
            chat_record = Chat(
                user_id=user_id, session_id=session_id, question=question,
                answer=answer, conversation_json=json.dumps(new_turns, ensure_ascii=False),
                file_path="||".join(file_paths) if file_paths else None,
            )
            db.session.add(chat_record)

        db.session.commit()
        logger.info("Chat saved, id=%s", chat_record.id)

        history_turns_used = sum(1 for msg in history_messages if msg.get("role") == "user")
        return jsonify({
            "chat_id": chat_record.id, "session_id": session_id,
            "question": question, "answer": answer,
            "history_turns_used": history_turns_used,
            "history_images_used": history_image_count,
            "has_rag_context": len(rag_context) > 0,
            "has_image": len(image_data_urls) > 0,
            "image_count": len(image_data_urls),
            "created_at": chat_record.created_at.isoformat(),
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error("Chat failed: %s", e, exc_info=True)
        return jsonify({"error": f"处理失败: {str(e)}"}), 500


@bp.route("/chat/history", methods=["GET"])
@jwt_required()
def get_chat_history():
    try:
        user_id = int(get_jwt_identity())
        requested_session_id = (request.args.get("session_id") or "").strip()
        page = request.args.get("page", 1, type=int)
        page_size = min(request.args.get("page_size", 50, type=int), 200)

        query = Chat.query.filter_by(user_id=user_id)
        if requested_session_id:
            query = query.filter_by(session_id=requested_session_id)

        total = query.count()
        chat_records = query.order_by(Chat.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        result = []
        for c in chat_records:
            result.append({
                "id": c.id, "user_id": c.user_id, "session_id": c.session_id,
                "question": c.question, "answer": c.answer,
                "conversation_json": c.conversation_json, "file_path": c.file_path,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })
        return jsonify({"data": result, "total": total, "page": page, "page_size": page_size, "total_pages": (total + page_size - 1) // page_size}), 200
    except Exception as e:
        logger.error("Get chat history failed: %s", e, exc_info=True)
        return jsonify({"error": f"获取历史记录失败: {str(e)}"}), 500


@bp.route("/chat/history/<int:chat_id>", methods=["DELETE"])
@jwt_required()
def delete_chat_history(chat_id):
    try:
        user_id = int(get_jwt_identity())
        chat_record = Chat.query.filter_by(id=chat_id, user_id=user_id).first()
        if not chat_record:
            return jsonify({"error": "聊天记录不存在或无权限删除"}), 404

        for stored_path in _parse_stored_file_paths(chat_record.file_path):
            if os.path.exists(stored_path):
                try:
                    os.remove(stored_path)
                except Exception as e:
                    logger.warning("File delete failed: %s", e)

        db.session.delete(chat_record)
        db.session.commit()
        return jsonify({"message": "聊天记录已删除"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"删除历史记录失败: {str(e)}"}), 500


@bp.route("/chat/history/session/<string:session_id>", methods=["DELETE"])
@jwt_required()
def delete_chat_history_by_session(session_id):
    try:
        user_id = int(get_jwt_identity())
        chat_records = Chat.query.filter_by(user_id=user_id, session_id=session_id).all()
        if not chat_records:
            return jsonify({"error": "会话不存在或无权限删除"}), 404

        all_paths = []
        for c in chat_records:
            all_paths.extend(_parse_stored_file_paths(c.file_path))
        for stored_path in set(all_paths):
            if os.path.exists(stored_path):
                try:
                    os.remove(stored_path)
                except Exception as e:
                    logger.warning("File delete failed: %s", e)

        Chat.query.filter_by(user_id=user_id, session_id=session_id).delete()
        db.session.commit()
        return jsonify({"message": "会话历史已删除"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"删除会话历史失败: {str(e)}"}), 500


@bp.route("/chat/history", methods=["DELETE"])
@jwt_required()
def delete_all_chat_history():
    try:
        user_id = int(get_jwt_identity())
        chat_records = Chat.query.filter_by(user_id=user_id).all()
        if not chat_records:
            return jsonify({"message": "无聊天记录"}), 200

        for c in chat_records:
            for stored_path in _parse_stored_file_paths(c.file_path):
                if os.path.exists(stored_path):
                    try:
                        os.remove(stored_path)
                    except Exception as e:
                        logger.warning("File delete failed: %s", e)

        Chat.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        return jsonify({"message": f"已删除 {len(chat_records)} 条聊天记录"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"删除所有历史记录失败: {str(e)}"}), 500
