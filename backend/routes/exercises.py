import json
import logging
import re

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, case

from models import db, ExerciseRecord
from services.llm_service import get_llm_client
from rag_manager import get_rag_manager

logger = logging.getLogger(__name__)

bp = Blueprint("exercises", __name__, url_prefix="/api/exercises")

CHAPTER_MAPPING = {
    "physical_layer": "物理层",
    "data_link_layer": "数据链路层",
    "network_layer": "网络层",
    "transport_layer": "传输层",
    "application_layer": "应用层",
}


def _build_rag_context(chapter_name):
    try:
        rag_manager = get_rag_manager()
        all_rag_docs = rag_manager.query(chapter_name, top_k=5, score_threshold=0.2)

        if not all_rag_docs:
            return f"请根据{chapter_name}的相关知识出题。", False

        unique_docs = {}
        for doc in all_rag_docs:
            source_file = doc["source"]
            if source_file not in unique_docs or doc["similarity_score"] > unique_docs[source_file]["similarity_score"]:
                unique_docs[source_file] = doc

        unique_docs_list = sorted(unique_docs.values(), key=lambda x: x["similarity_score"], reverse=True)[:3]
        rag_context = f"【{chapter_name}相关知识】\n"
        for i, doc in enumerate(unique_docs_list, 1):
            rag_context += f"\n【知识点 {i}】\n{doc['content'][:400]}\n"
        return rag_context, True

    except Exception as e:
        logger.warning("RAG retrieval for exercise failed: %s", e, exc_info=True)
        return f"请根据{chapter_name}的相关知识出题。", False


def _parse_llm_json(raw_text):
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', raw_text).strip()
    json_start = cleaned.find("{")
    json_end = cleaned.rfind("}") + 1
    if json_start != -1 and json_end > json_start:
        return json.loads(cleaned[json_start:json_end])
    return None


@bp.route("/generate", methods=["POST"])
@jwt_required()
def generate_exercise():
    try:
        data = request.get_json()
        chapter = data.get("chapter", "")
        question_type = data.get("question_type", "choice")
        difficulty = data.get("difficulty", "medium")
        previous_questions = data.get("previous_questions", [])

        chapter_name = CHAPTER_MAPPING.get(chapter, "计算机网络")
        logger.info("Generate exercise: chapter=%s, type=%s, diff=%s", chapter_name, question_type, difficulty)

        rag_context, has_rag = _build_rag_context(chapter_name)

        previous_questions_hint = ""
        if previous_questions:
            prev_list = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(previous_questions[-10:]))
            previous_questions_hint = (
                f"\n\n【重要 - 禁止重复】以下是已经出过的题目，你必须出一道完全不同的新题：\n{prev_list}\n"
                "新题目必须考查不同的知识点，使用不同的问法和场景。"
            )

        if question_type == "choice":
            system_prompt = f"""你是一个专业的计算机网络教学专家，现在需要为学生出一道关于"{chapter_name}"的选择题。

【核心约束】
1. 题目必须严格涉及"{chapter_name}"的知识点，不能超出该章节范围
2. 提供恰好4个选项(A、B、C、D)，只有1个正确答案
3. 难度等级"{difficulty}"：easy=基础概念题，medium=理解应用题，hard=综合分析题
{previous_questions_hint}

【返回格式】严格按照以下 JSON 格式返回：
{{"question": "完整的题目文本", "options": ["A选项文本", "B选项文本", "C选项文本", "D选项文本"], "correct_answer": "A/B/C/D", "explanation": "解析说明"}}

【知识库背景】
{rag_context}"""
            user_prompt = f"请为学生出一道关于{chapter_name}的{difficulty}难度选择题。请立即生成题目并返回 JSON。"
        else:
            system_prompt = f"""你是一个专业的计算机网络教学专家，现在需要为学生出一道关于"{chapter_name}"的简答题。

【核心约束】
1. 题目必须严格涉及"{chapter_name}"的知识点
2. 学生答案应该在1-5个句子左右
3. 难度等级"{difficulty}"：easy=考查概念定义，medium=理解应用，hard=综合分析
{previous_questions_hint}

【返回格式】严格按照以下 JSON 格式返回：
{{"question": "完整的题目文本", "sample_answer": "标准答案", "key_points": ["关键知识点1", "关键知识点2"], "explanation": "解析说明"}}

【知识库背景】
{rag_context}"""
            user_prompt = f"请为学生出一道关于{chapter_name}的{difficulty}难度简答题。请立即生成题目并返回 JSON。"

        client = get_llm_client()
        resp = client.chat.completions.create(
            model="qwen-max",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.95,
            max_tokens=800,
            stream=False,
        )

        answer = (resp.choices[0].message.content or "").strip()
        if not answer:
            return jsonify({"error": "无法生成题目"}), 500

        exercise_data = _parse_llm_json(answer)
        if exercise_data is None:
            exercise_data = {"question": answer, "type": question_type, "difficulty": difficulty, "chapter": chapter_name}

        if question_type == "choice":
            if "options" not in exercise_data or len(exercise_data.get("options", [])) < 4:
                exercise_data["options"] = ["选项A", "选项B", "选项C", "选项D"]
            if "correct_answer" not in exercise_data:
                exercise_data["correct_answer"] = "A"
        else:
            exercise_data.setdefault("key_points", ["关键概念", "核心原理"])
            exercise_data.setdefault("sample_answer", "请参考标准答案")

        exercise_data.setdefault("question", user_prompt)
        exercise_data.setdefault("explanation", "详见课程教材")
        exercise_data["chapter"] = chapter_name
        exercise_data["difficulty"] = difficulty
        exercise_data["question_type"] = question_type

        logger.info("Exercise generated: %.60s", exercise_data["question"])

        return jsonify({
            "status": "success", "exercise": exercise_data,
            "question_type": question_type, "difficulty": difficulty,
            "chapter": chapter_name, "has_rag_context": has_rag,
        }), 200

    except Exception as e:
        logger.error("Generate exercise failed: %s", e, exc_info=True)
        return jsonify({"error": f"生成题目失败: {str(e)}"}), 500


@bp.route("/submit", methods=["POST"])
@jwt_required()
def submit_exercise():
    try:
        data = request.get_json()
        question = data.get("question")
        question_type = data.get("question_type")
        user_answer = data.get("user_answer")
        correct_answer = data.get("correct_answer")
        chapter = data.get("chapter", "")
        difficulty = data.get("difficulty", "")
        options = data.get("options")
        explanation = data.get("explanation", "")
        key_points = data.get("key_points")
        sample_answer = data.get("sample_answer", "")

        user_id = int(get_jwt_identity())
        result_data = {}

        if question_type == "choice":
            is_correct = user_answer.upper() == correct_answer.upper()
            result_data = {
                "status": "success", "is_correct": is_correct,
                "score": 100 if is_correct else 0,
                "feedback": "回答正确！" if is_correct else "回答错误，请再想想",
                "correct_answer": correct_answer, "explanation": explanation,
            }
        else:
            try:
                rag_manager = get_rag_manager()
                retrieved_docs = rag_manager.retrieve(question, k=3)
                context = "\n".join([doc["content"][:300] for doc in retrieved_docs])
            except Exception:
                context = ""

            grading_prompt = (
                "你是一个专业的计算机网络教学评卷老师。请评判学生的简答题答案是否正确，并给出相应的反馈。"
                "回复时不要使用markdown格式。\n\n"
                f"题目: {question}\n\n背景知识: {context}\n\n"
                "请返回 JSON 格式，包含以下字段:\n"
                "- is_correct: true/false\n- score: 0-100 的得分\n"
                "- feedback: 评价和建议（中文）\n- key_points: 应该包含的关键点（列表）"
            )

            client = get_llm_client()
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": grading_prompt},
                    {"role": "user", "content": f"学生答案: {user_answer}"},
                ],
                temperature=0.5, max_tokens=500, stream=False,
            )

            answer = (resp.choices[0].message.content or "").strip()
            if not answer:
                return jsonify({"error": "无法评分"}), 500

            result_data = _parse_llm_json(answer) or {"feedback": answer, "score": 0, "is_correct": False}
            result_data.setdefault("is_correct", False)
            result_data.setdefault("score", 0)
            result_data.setdefault("feedback", "")
            result_data["status"] = "success"
            if sample_answer:
                result_data["correct_answer"] = sample_answer

        is_correct = result_data.get("is_correct", False)
        score = result_data.get("score", 100 if is_correct else 0)

        record = ExerciseRecord(
            user_id=user_id, chapter=chapter, question_type=question_type,
            difficulty=difficulty, question=question,
            options_json=json.dumps(options, ensure_ascii=False) if options else None,
            correct_answer=correct_answer or sample_answer,
            user_answer=user_answer, is_correct=is_correct, score=score,
            feedback=result_data.get("feedback", ""),
            explanation=explanation or result_data.get("explanation", ""),
            key_points_json=json.dumps(
                key_points or result_data.get("key_points"), ensure_ascii=False
            ) if (key_points or result_data.get("key_points")) else None,
        )
        db.session.add(record)
        db.session.commit()
        result_data["record_id"] = record.id
        return jsonify(result_data), 200

    except Exception as e:
        db.session.rollback()
        logger.error("Submit exercise failed: %s", e, exc_info=True)
        return jsonify({"error": f"提交失败: {str(e)}"}), 500


@bp.route("/history", methods=["GET"])
@jwt_required()
def get_exercise_history():
    try:
        user_id = int(get_jwt_identity())
        page = request.args.get("page", 1, type=int)
        page_size = min(request.args.get("page_size", 20, type=int), 100)

        query = ExerciseRecord.query.filter_by(user_id=user_id)

        chapter = request.args.get("chapter")
        if chapter:
            query = query.filter_by(chapter=chapter)
        question_type = request.args.get("question_type")
        if question_type:
            query = query.filter_by(question_type=question_type)
        is_correct = request.args.get("is_correct")
        if is_correct is not None and is_correct != "":
            query = query.filter_by(is_correct=is_correct.lower() == "true")

        total = query.count()
        records = query.order_by(ExerciseRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return jsonify({
            "data": [r.to_dict() for r in records], "total": total,
            "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/stats", methods=["GET"])
@jwt_required()
def get_exercise_stats():
    try:
        user_id = int(get_jwt_identity())

        totals = db.session.query(
            func.count(ExerciseRecord.id).label("total"),
            func.sum(case((ExerciseRecord.is_correct == True, 1), else_=0)).label("correct"),
        ).filter_by(user_id=user_id).one()

        total = totals.total or 0
        correct = int(totals.correct or 0)

        by_chapter_rows = db.session.query(
            func.coalesce(ExerciseRecord.chapter, "未分类").label("chapter"),
            func.count(ExerciseRecord.id).label("total"),
            func.sum(case((ExerciseRecord.is_correct == True, 1), else_=0)).label("correct"),
        ).filter_by(user_id=user_id).group_by(ExerciseRecord.chapter).all()

        by_chapter = {row.chapter: {"total": row.total, "correct": int(row.correct or 0)} for row in by_chapter_rows}

        return jsonify({
            "total": total, "correct": correct, "wrong": total - correct,
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
            "by_chapter": by_chapter,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/history/<int:record_id>", methods=["DELETE"])
@jwt_required()
def delete_exercise_record(record_id):
    try:
        user_id = int(get_jwt_identity())
        record = ExerciseRecord.query.filter_by(id=record_id, user_id=user_id).first()
        if not record:
            return jsonify({"error": "记录不存在"}), 404
        db.session.delete(record)
        db.session.commit()
        return jsonify({"message": "已删除"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/history", methods=["DELETE"])
@jwt_required()
def clear_exercise_history():
    try:
        user_id = int(get_jwt_identity())
        ExerciseRecord.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        return jsonify({"message": "已清空所有练习记录"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
