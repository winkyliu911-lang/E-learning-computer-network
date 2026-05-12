import datetime
import logging
import os
from pathlib import Path

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename

from rag_manager import get_rag_manager

logger = logging.getLogger(__name__)

bp = Blueprint("rag", __name__, url_prefix="/api/rag")

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@bp.route("/upload-documents", methods=["POST"])
@jwt_required()
def upload_rag_documents():
    try:
        if "files" not in request.files:
            return jsonify({"error": "请上传至少一个文件"}), 400

        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "未找到上传的文件"}), 400

        file_paths = []
        for file in files:
            if file and file.filename:
                if not file.filename.lower().endswith((".pdf", ".docx")):
                    continue
                filename = f"rag_{int(datetime.datetime.utcnow().timestamp())}_{secure_filename(file.filename)}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                file_paths.append(file_path)
                logger.info("RAG file saved: %s", file_path)

        if not file_paths:
            return jsonify({"error": "未找到有效的 PDF 或 DOCX 文件"}), 400

        rag_manager = get_rag_manager()
        results = rag_manager.add_documents(file_paths, document_source="user_uploaded")

        return jsonify({
            "status": "success",
            "processed_files": results["processed_files"],
            "total_chunks": results["total_chunks"],
            "errors": results["errors"],
        }), 200

    except Exception as e:
        logger.error("RAG upload failed: %s", e, exc_info=True)
        return jsonify({"error": f"处理失败: {str(e)}"}), 500


@bp.route("/stats", methods=["GET"])
@jwt_required()
def rag_stats():
    try:
        rag_manager = get_rag_manager()
        stats = rag_manager.get_db_stats()
        return jsonify(stats), 200
    except Exception as e:
        logger.error("RAG stats failed: %s", e)
        return jsonify({"error": f"获取失败: {str(e)}"}), 500


@bp.route("/search", methods=["POST"])
@jwt_required()
def rag_search():
    try:
        data = request.get_json()
        if not data or not data.get("query"):
            return jsonify({"error": "查询文本不能为空"}), 400

        query = data.get("query")
        top_k = data.get("top_k", 5)
        mode = data.get("mode", "hybrid")

        rag_manager = get_rag_manager()
        results = rag_manager.query(query, top_k=top_k, score_threshold=0.3, mode=mode)

        return jsonify({
            "status": "success", "query": query,
            "results_count": len(results), "results": results,
        }), 200

    except Exception as e:
        logger.error("RAG search failed: %s", e)
        return jsonify({"error": f"搜索失败: {str(e)}"}), 500


@bp.route("/clear", methods=["POST"])
@jwt_required()
def clear_rag_db():
    try:
        rag_manager = get_rag_manager()
        result = rag_manager.clear_db()
        return jsonify(result), 200
    except Exception as e:
        logger.error("RAG clear failed: %s", e)
        return jsonify({"error": f"清空失败: {str(e)}"}), 500


@bp.route("/init", methods=["POST"])
@jwt_required()
def init_rag_db():
    try:
        documents_dir = Path(__file__).parent.parent.parent / "Data"

        file_paths = list(documents_dir.glob("*.pdf")) + list(documents_dir.glob("*.docx")) + list(documents_dir.glob("*.md"))

        if not file_paths:
            return jsonify({
                "status": "warning",
                "message": "Data 目录中未找到文件",
                "documents_dir": str(documents_dir),
            }), 200

        rag_manager = get_rag_manager()
        results = rag_manager.add_documents([str(p) for p in file_paths], document_source="builtin")

        return jsonify({
            "status": "success",
            "processed_files": results["processed_files"],
            "total_chunks": results["total_chunks"],
            "errors": results["errors"],
            "documents_dir": str(documents_dir),
        }), 200

    except Exception as e:
        logger.error("RAG init failed: %s", e, exc_info=True)
        return jsonify({"error": f"初始化失败: {str(e)}"}), 500
