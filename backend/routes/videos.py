import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from models import db, CourseVideo

logger = logging.getLogger(__name__)

bp = Blueprint("videos", __name__, url_prefix="/api")


@bp.route("/videos", methods=["GET"])
def get_videos():
    category = request.args.get("category")
    query = CourseVideo.query
    if category:
        query = query.filter_by(category=category)
    videos = query.all()
    return jsonify([v.to_dict() for v in videos]), 200


@bp.route("/videos/<int:video_id>", methods=["GET"])
def get_video(video_id):
    video = CourseVideo.query.get(video_id)
    if not video:
        return jsonify({"error": "视频不存在"}), 404
    return jsonify(video.to_dict()), 200


@bp.route("/videos", methods=["POST"])
@jwt_required()
def create_video():
    data = request.get_json()
    if not data or not data.get("title") or not data.get("video_url"):
        return jsonify({"error": "缺少必要的字段"}), 400

    video = CourseVideo(
        title=data["title"],
        description=data.get("description"),
        category=data.get("category", "uncategorized"),
        video_url=data["video_url"],
        duration=data.get("duration"),
    )
    db.session.add(video)
    db.session.commit()
    return jsonify(video.to_dict()), 201
