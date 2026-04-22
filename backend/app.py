from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from flask_jwt_extended import decode_token
from config import Config
from models import db, User, CourseVideo, Textbook, Chat, ExerciseRecord, Note
import os
import datetime
import json
import uuid
from werkzeug.utils import secure_filename
from openai import OpenAI
from rag_manager import get_rag_manager
from file_extractor import convert_upload_to_images
from PIL import Image
import io
import base64
import bcrypt
from sqlalchemy import text


app = Flask(__name__)
app.config.from_object(Config)

# 使用 OpenAI 兼容的通义千问客户端（保留硬编码 API key，增加兼容性处理）
# 记录初始化异常以便后续在 API 中返回更详细的诊断信息
INIT_ERROR = None
OPENAI_CLIENT = None
try:
    try:
        OPENAI_CLIENT = OpenAI(
            api_key="sk-45af25c9a2974ae7bbb8fcf87bb01f5e",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    except TypeError as e:
        # 某些 OpenAI 客户端实现不接受 base_url 或其他额外参数，退回到更简单的初始化
        print(f"⚠️ OpenAI 客户端初始化兼容性问题: {e}. 尝试不带 base_url 的初始化。")
        try:
            OPENAI_CLIENT = OpenAI(
                api_key="sk-45af25c9a2974ae7bbb8fcf87bb01f5e",
            )
        except Exception as e2:
            INIT_ERROR = f"第二次初始化失败: {e2} (首个兼容性异常: {e})"
            print(f"⚠️ OpenAI 客户端初始化失败: {INIT_ERROR}")
            OPENAI_CLIENT = None
except Exception as e:
    INIT_ERROR = str(e)
    print(f"⚠️ OpenAI 客户端初始化警告: {INIT_ERROR}")
    import traceback
    traceback.print_exc()
    OPENAI_CLIENT = None

def verify_user(username, password):
    """使用 SQLAlchemy 的 User 模型验证用户（替代独立的 users.db）。"""
    try:
        user = User.query.filter_by(username=username).first()
        if not user:
            return False
        return user.check_password(password)
    except Exception:
        return False

MAX_HISTORY_MESSAGE_CHARS = 1000


def _trim_text(text, max_chars):
    """截断历史文本，防止提示词过长。"""
    if not text:
        return ""
    cleaned = str(text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + "..."


def build_history_messages(history_items):
    """将前端传入的当前会话历史转换为 OpenAI 兼容 messages。"""
    messages = []
    if not isinstance(history_items, list):
        return messages

    for item in history_items:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        if role not in ("user", "assistant"):
            continue

        text = _trim_text(item.get("content"), MAX_HISTORY_MESSAGE_CHARS)
        if not text or text.startswith("❌"):
            continue

        messages.append({
            "role": role,
            "content": [{"type": "text", "text": text}]
        })
    return messages


def build_session_history_messages(user_id, session_id):
    """从数据库按会话读取历史，并恢复历史轮次中的图片输入。"""
    messages = []
    history_image_count = 0
    if not session_id:
        return messages, history_image_count

    try:
        records = Chat.query.filter_by(user_id=user_id, session_id=session_id).order_by(Chat.created_at.asc()).all()
    except Exception as e:
        print(f"[Chat API] ⚠️ 读取会话历史失败: {e}")
        return messages, history_image_count

    # 新结构：同一 session 只存一条，conversation_json 保存完整会话
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

                role = item.get('role')
                if role not in ('user', 'assistant'):
                    continue

                text_content = _trim_text(item.get('content'), MAX_HISTORY_MESSAGE_CHARS)
                if not text_content:
                    continue

                if role == 'user':
                    user_content = [{"type": "text", "text": text_content}]
                    for stored_path in item.get('file_paths') or []:
                        data_url = extract_image_data_url_from_file(stored_path)
                        if data_url:
                            user_content.append({
                                "type": "image_url",
                                "image_url": {"url": data_url}
                            })
                            history_image_count += 1
                    messages.append({"role": "user", "content": user_content})
                else:
                    if text_content.startswith("❌"):
                        continue
                    messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": text_content}]
                    })

            return messages, history_image_count

    # 旧结构兼容：每轮一条记录
    for record in records:
        question_text = _trim_text(record.question, MAX_HISTORY_MESSAGE_CHARS)
        answer_text = _trim_text(record.answer, MAX_HISTORY_MESSAGE_CHARS)
        if not question_text:
            continue

        user_content = [{"type": "text", "text": question_text}]
        for stored_path in parse_stored_file_paths(record.file_path):
            data_url = extract_image_data_url_from_file(stored_path)
            if data_url:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": data_url}
                })
                history_image_count += 1

        messages.append({"role": "user", "content": user_content})

        if answer_text and not answer_text.startswith("❌"):
            messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": answer_text}]
            })

    return messages, history_image_count


def call_qwen_api(question, context="", image_data_urls=None, history_messages=None):
    """
    使用 OpenAI 兼容接口调用通义千问（qwen3-omni-flash），支持文本+可选图片输入，返回文本
    
    Args:
        question: 用户问题文本
        context: 背景信息或 RAG 检索结果
       
    """
    if OPENAI_CLIENT is None:
        err_msg = "LLM 客户端未初始化。请检查后端启动日志或 API 客户端初始化配置。"
        if INIT_ERROR:
            err_msg += f" 初始化错误: {INIT_ERROR}"
        raise RuntimeError(err_msg)

    try:
        system_prompt = "你是一个专业的计算机网络知识助手，使用中文回答，简明准确，必要时给出示例。回复时不要使用任何markdown格式，不要使用#号、*号、-号列表等标记符号，直接用纯文本和数字编号回答。"
        
        # 构建消息内容
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # 先拼接历史多轮（如果有）
        if history_messages:
            messages.extend(history_messages)

        # 构建用户消息 - 多模态输入（文本 + 可选图片）
        user_content = []

        # 添加文本内容
        text_parts = []
        if context:
            text_parts.append(f"背景信息：{context}")
        text_parts.append(f"用户问题：{question}")
        text_content = "\n\n".join(text_parts)
        
        user_content.append({"type": "text", "text": text_content})

        # 添加图像内容（如果存在，支持多张）
        if image_data_urls:
            for image_data_url in image_data_urls:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": image_data_url
                    }
                })

        messages.append({
            "role": "user",
            "content": user_content
        })

        if OPENAI_CLIENT is None:
            err_msg = "LLM 客户端未初始化。请检查后端启动日志或 API 客户端初始化配置。"
            if INIT_ERROR:
                err_msg += f" 初始化错误: {INIT_ERROR}"
            raise RuntimeError(err_msg)

        completion = OPENAI_CLIENT.chat.completions.create(
            model="qwen-vl-max",
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
            stream=True,
        )

        # 流式聚合文本输出
        answer_parts = []
        for chunk in completion:
            choices = getattr(chunk, "choices", None) or (chunk.get("choices") if isinstance(chunk, dict) else None)
            if not choices:
                continue

            first_choice = choices[0]
            if isinstance(first_choice, dict):
                delta = first_choice.get("delta") or {}
            else:
                delta = getattr(first_choice, "delta", None)

            if isinstance(delta, dict):
                delta_content = delta.get("content")
            else:
                delta_content = getattr(delta, "content", None)

            if isinstance(delta_content, str):
                answer_parts.append(delta_content)
            elif isinstance(delta_content, list):
                for part in delta_content:
                    if isinstance(part, dict):
                        text_piece = part.get("text")
                    else:
                        text_piece = getattr(part, "text", None)
                    if text_piece:
                        answer_parts.append(text_piece)

        answer = "".join(answer_parts).strip()

        import re
        answer = re.sub(r'<think>[\s\S]*?</think>', '', answer).strip()

        if not answer:
            print("[call_qwen_api] 无法从流式响应中解析文本。")
            return "❌ 无法解析 LLM 响应，请查看后端日志"

        return answer

    except Exception as e:
        print("[call_qwen_api] 异常：", str(e))
        raise
# ...existing code...
# ...existing code...

# 初始化扩展
db.init_app(app)
CORS(app)
jwt = JWTManager(app)

# 在应用上下文中确保数据库表存在（首次启动时创建）
with app.app_context():
    try:
        db.create_all()
        table_columns = db.session.execute(text("PRAGMA table_info(chats)")).fetchall()
        column_names = [row[1] for row in table_columns]
        if 'session_id' not in column_names:
            db.session.execute(text("ALTER TABLE chats ADD COLUMN session_id VARCHAR(64)"))
            db.session.commit()
            print("✅ 数据库迁移：已为 chats 表新增 session_id 字段")
        if 'conversation_json' not in column_names:
            db.session.execute(text("ALTER TABLE chats ADD COLUMN conversation_json TEXT"))
            db.session.commit()
            print("✅ 数据库迁移：已为 chats 表新增 conversation_json 字段")
        print("✅ 数据库初始化：表已创建或已存在（elearning.db）")
    except Exception as e:
        print(f"⚠️ 数据库初始化失败: {e}")

@jwt.user_identity_loader
def user_identity_lookup(identity):
    return str(identity)


# JWT 错误回调，便于调试和返回更友好的错误信息
@jwt.unauthorized_loader
def jwt_unauthorized_callback(reason):
    print("[JWT] unauthorized:", reason)
    return jsonify({'error': 'Authorization header missing or malformed', 'msg': reason}), 401


@jwt.invalid_token_loader
def jwt_invalid_token_callback(reason):
    print("[JWT] invalid token:", reason)
    return jsonify({'error': 'Invalid token', 'msg': reason}), 422


@jwt.expired_token_loader
def jwt_expired_callback(jwt_header, jwt_payload):
    print("[JWT] expired token")
    return jsonify({'error': 'Token expired'}), 401


@app.route('/api/debug/decode-token', methods=['POST'])
def debug_decode_token():
    """开发时用于解码并查看 token 内容（仅用于本地调试）"""
    data = request.get_json(silent=True) or {}
    token = data.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    if not token:
        return jsonify({'error': 'token missing (provide JSON {"token":"..."} or Authorization header)'}), 400
    try:
        payload = decode_token(token)
        return jsonify({'decoded': payload}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# 创建上传文件夹
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 配置教科书文件夹路径
TEXTBOOK_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'public')

# ==================== 文件服务 API ====================

@app.route('/api/files/textbooks/<path:filename>', methods=['GET'])
def serve_textbook(filename):
    """提供教科书文件下载服务"""
    from flask import send_file
    from urllib.parse import unquote
    
    try:
        # 对 URL 编码的文件名进行解码（处理中文字符）
        decoded_filename = unquote(filename)
        
        print(f"[文件服务] 请求文件: {decoded_filename}")
        
        # 构建文件路径
        file_path = os.path.join(TEXTBOOK_FOLDER, decoded_filename)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"[文件服务] 文件不存在: {file_path}")
            return jsonify({'error': f'文件不存在: {decoded_filename}'}), 404
        
        # 检查路径是否在允许的目录内（安全检查）
        real_path = os.path.abspath(file_path)
        real_textbook_folder = os.path.abspath(TEXTBOOK_FOLDER)
        if not real_path.startswith(real_textbook_folder):
            print(f"[文件服务] 无权访问: {real_path}")
            return jsonify({'error': '无权访问该文件'}), 403
        
        # 根据文件类型返回合适的 MIME 类型
        mime_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.md': 'text/markdown'
        }
        
        _, ext = os.path.splitext(file_path)
        mime_type = mime_types.get(ext.lower(), 'application/octet-stream')
        
        print(f"[文件服务] ✅ 提供文件: {file_path} (类型: {mime_type})")
        return send_file(file_path, mimetype=mime_type)
    
    except Exception as e:
        print(f"[文件服务] ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'文件访问失败: {str(e)}'}), 500

# ==================== 认证相关API ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password') or not data.get('email'):
        return jsonify({'error': '缺少必要的字段'}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': '用户名已存在'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': '邮箱已存在'}), 400
    
    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    return jsonify({
        'message': '注册成功',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict()
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登陆"""
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': '缺少必要的字段'}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    
    if not user or not user.check_password(data['password']):
        return jsonify({'error': '用户名或密码错误'}), 401
    
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    return jsonify({
        'message': '登陆成功',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict()
    }), 200


@app.route('/api/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_access_token():
    """使用 refresh token 刷新 access token"""
    try:
        user_id = get_jwt_identity()
        new_access_token = create_access_token(identity=str(user_id))
        return jsonify({'access_token': new_access_token}), 200
    except Exception as e:
        return jsonify({'error': f'刷新 token 失败: {str(e)}'}), 401

# ==================== 课程视频API ====================

@app.route('/api/videos', methods=['GET'])
def get_videos():
    """获取所有课程视频"""
    category = request.args.get('category')
    
    query = CourseVideo.query
    if category:
        query = query.filter_by(category=category)
    
    videos = query.all()
    return jsonify([v.to_dict() for v in videos]), 200

@app.route('/api/videos/<int:video_id>', methods=['GET'])
def get_video(video_id):
    """获取单个课程视频"""
    video = CourseVideo.query.get(video_id)
    if not video:
        return jsonify({'error': '视频不存在'}), 404
    
    return jsonify(video.to_dict()), 200

@app.route('/api/videos', methods=['POST'])
@jwt_required()
def create_video():
    """创建课程视频（仅管理员）"""
    data = request.get_json()
    
    if not data or not data.get('title') or not data.get('video_url'):
        return jsonify({'error': '缺少必要的字段'}), 400
    
    video = CourseVideo(
        title=data['title'],
        description=data.get('description'),
        category=data.get('category', 'uncategorized'),
        video_url=data['video_url'],
        duration=data.get('duration')
    )
    
    db.session.add(video)
    db.session.commit()
    
    return jsonify(video.to_dict()), 201

# ==================== 课本API ====================

@app.route('/api/textbooks', methods=['GET'])
def get_textbooks():
    """获取所有课本"""
    category = request.args.get('category')
    
    query = Textbook.query
    if category:
        query = query.filter_by(category=category)
    
    textbooks = query.all()
    return jsonify([t.to_dict() for t in textbooks]), 200

@app.route('/api/textbooks/<int:textbook_id>', methods=['GET'])
def get_textbook(textbook_id):
    """获取单个课本"""
    textbook = Textbook.query.get(textbook_id)
    if not textbook:
        return jsonify({'error': '课本不存在'}), 404
    
    return jsonify(textbook.to_dict()), 200

@app.route('/api/textbooks', methods=['POST'])
@jwt_required()
def create_textbook():
    """创建课本（仅管理员）"""
    data = request.get_json()
    
    if not data or not data.get('title') or not data.get('content'):
        return jsonify({'error': '缺少必要的字段'}), 400
    
    textbook = Textbook(
        title=data['title'],
        description=data.get('description'),
        category=data.get('category', 'uncategorized'),
        content=data['content']
    )
    
    db.session.add(textbook)
    db.session.commit()
    
    return jsonify(textbook.to_dict()), 201

# ==================== 聊天API ====================

def extract_image_data_url_from_file(file_path):
    """将本地图片文件转换为 data URL。"""
    try:
        ext_to_mime = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp',
        }

        ext = os.path.splitext(file_path)[1].lower()
        mime_type = ext_to_mime.get(ext)
        if not mime_type:
            return None

        with open(file_path, 'rb') as f:
            encoded = base64.b64encode(f.read()).decode('utf-8')
        return f"data:{mime_type};base64,{encoded}"
    except Exception as e:
        print(f"[Chat] 图片转 data URL 异常: {e}")
        return None


def parse_stored_file_paths(file_path_value):
    """从数据库中的 file_path 字段解析出多个文件路径。"""
    if not file_path_value:
        return []
    return [p for p in file_path_value.split('||') if p]


@app.route('/api/chat', methods=['POST'])
@jwt_required()
def chat():
    """
    处理聊天请求的 API 端点 - 支持 RAG + 多模态文件
    
    请求格式: POST /api/chat
    请求体（JSON）: {
        "question": "什么是 TCP 三次握手？",
        "use_rag": true,  // 是否使用 RAG 检索
        "context": "可选的背景信息"
    }
    
    或请求体（form-data）:
        - question: 问题
        - use_rag: 是否使用 RAG（true/false）
        - context: 可选背景信息
        - session_id: 当前聊天会话 ID
        - history_messages: 当前聊天界面历史（JSON 字符串）
        - files: 可选上传图片（可多张）
    """
    print("[Chat API] headers:", dict(request.headers))
    data = request.get_json(silent=True)
    file_paths = []
    rag_context = ""
    image_data_urls = []

    # 如果不是 JSON，尝试从 form-data 中读取
    if not data:
        form = request.form
        if form and form.get('question'):
            data = {
                'question': form.get('question'),
                'context': form.get('context', ''),
                'use_rag': form.get('use_rag', 'true').lower() == 'true',
                'session_id': form.get('session_id', ''),
                'history_messages': form.get('history_messages', '[]')
            }
        else:
            print("[Chat API] 无法解析请求体为 JSON 或 form-data 中未包含 question")
            return jsonify({'error': '请求体必须为 JSON 或 form-data，并包含字段 question'}), 400

    user_id_raw = get_jwt_identity()
    try:
        user_id = int(user_id_raw)
    except Exception:
        user_id = user_id_raw

    question = (data.get('question') or '').strip()
    context = (data.get('context') or '').strip()
    use_rag = data.get('use_rag', True)
    session_id = (data.get('session_id') or '').strip()
    history_messages_raw = data.get('history_messages', [])

    if not session_id:
        session_id = str(uuid.uuid4())
    if len(session_id) > 64:
        return jsonify({'error': 'session_id 过长，请不超过 64 字符'}), 400

    if isinstance(history_messages_raw, str):
        try:
            history_items = json.loads(history_messages_raw) if history_messages_raw else []
        except Exception:
            history_items = []
    elif isinstance(history_messages_raw, list):
        history_items = history_messages_raw
    else:
        history_items = []

    # 如果是 form-data 并带文件，保存并转换为图片输入（支持 files 多文件，兼容 file 单文件）
    upload_files = request.files.getlist('files')
    if not upload_files and 'file' in request.files:
        upload_files = [request.files['file']]

    if upload_files:
        allowed_file_ext = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.pdf', '.docx'}
        allowed_mime_prefix = (
            'image/',
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/octet-stream',  # 某些浏览器对 docx 会给这个类型
        )

        for index, file in enumerate(upload_files):
            if not file or not file.filename:
                continue

            ext = os.path.splitext(file.filename)[1].lower()
            content_type = (file.mimetype or '').lower()
            if ext not in allowed_file_ext:
                return jsonify({'error': '仅支持上传图片、PDF、DOCX 文件'}), 400

            mime_ok = any(content_type.startswith(prefix) for prefix in allowed_mime_prefix)
            if not mime_ok and ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}:
                return jsonify({'error': '图片文件类型不正确，请重新上传'}), 400

            filename = f"{user_id}_{int(datetime.datetime.utcnow().timestamp())}_{index}_{secure_filename(file.filename)}"
            current_file_path = os.path.join(UPLOAD_FOLDER, filename)
            try:
                file.save(current_file_path)
                file_paths.append(current_file_path)
                print(f"[Chat API] 文件已保存: {current_file_path}")

                # 支持图片直接输入，或 PDF/DOCX 转分页图片后逐页输入
                converted_image_paths = convert_upload_to_images(
                    current_file_path,
                    output_dir=UPLOAD_FOLDER,
                    owner_prefix=str(user_id)
                )

                converted_count = 0
                for generated_path in converted_image_paths:
                    data_url = extract_image_data_url_from_file(generated_path)
                    if data_url:
                        image_data_urls.append(data_url)
                        converted_count += 1
                        if generated_path not in file_paths:
                            file_paths.append(generated_path)

                print(f"[Chat API] {os.path.basename(current_file_path)} 已生成 {converted_count} 张可用图片")
            except Exception as e:
                print(f"[Chat API] 保存文件失败: {e}")

    if upload_files and not image_data_urls:
        return jsonify({'error': '上传文件处理失败，请检查 PDF/DOCX 内容或重试'}), 400

    # 输入验证
    if not question:
        return jsonify({'error': '问题不能为空'}), 400

    if len(question) > 2000:
        return jsonify({'error': '问题过长，请不超过 2000 字'}), 400

    try:
        print(f"\n[Chat API] 收到请求 - 用户ID: {user_id}, 问题: {question[:50]}..., use_rag: {use_rag}")
        print(f"[Chat API] 当前会话ID: {session_id}")

        # ========== 步骤 1: 从 RAG 数据库检索相关文档 ==========
        if use_rag:
            try:
                rag_manager = get_rag_manager()
                # 先检索更多文档，然后去重和筛选
                rag_docs = rag_manager.query(question, top_k=10, score_threshold=0.3)
                
                if rag_docs:
                    # 去重：保留来自不同文件的文档，并按相似度排序
                    unique_docs = {}
                    for doc in rag_docs:
                        source_file = doc['source']
                        # 如果该文件还没有被添加，或者新的相似度更高，则保留
                        if source_file not in unique_docs or doc['similarity_score'] > unique_docs[source_file]['similarity_score']:
                            unique_docs[source_file] = doc
                    
                    # 按相似度排序，只保留前 3 个不同的文档源
                    unique_docs_list = sorted(unique_docs.values(), key=lambda x: x['similarity_score'], reverse=True)[:3]
                    
                    print(f"\n[Chat API] 📚 RAG 检索结果详情:")
                    print(f"[Chat API] ═══════════════════════════════════════════")
                    print(f"[Chat API] 用户问题: {question}")
                    print(f"[Chat API] 检索到 {len(unique_docs_list)} 个不同来源的相关文档")
                    print(f"[Chat API] ───────────────────────────────────────────")
                    
                    # 构建 RAG 上下文
                    rag_context = "📚 相关知识库内容:\n"
                    
                    for i, doc in enumerate(unique_docs_list, 1):
                        source = doc['source']
                        similarity = doc['similarity_score']
                        
                        print(f"[Chat API] 【文档 {i}】")
                        print(f"[Chat API]   📄 来源: {source}")
                        print(f"[Chat API]   📊 相似度: {similarity:.2%}")
                        print(f"[Chat API]   📝 内容预览: {doc['content'][:100]}...")
                        print(f"[Chat API] ───────────────────────────────────────────")
                        
                        rag_context += f"\n【文档 {i} 来自: {source} (相似度: {similarity:.2%})】\n"
                        rag_context += doc['content'][:300] + "...\n"
                    
                    print(f"[Chat API] 📋 本次检索涉及的文档来源:")
                    for idx, doc in enumerate(unique_docs_list, 1):
                        print(f"[Chat API]   [{idx}] {doc['source']}")
                    print(f"[Chat API] ═══════════════════════════════════════════\n")
                    
                else:
                    print("[Chat API] ⚠️  RAG 检索无结果")
                    rag_context = ""
                    
            except Exception as e:
                print(f"[Chat API] ⚠️  RAG 检索异常: {e}")
                import traceback
                traceback.print_exc()
                rag_context = ""

        # ========== 步骤 2: 组合上下文 ==========
        combined_context = ""
        if rag_context:
            combined_context = rag_context
        if context:
            combined_context += f"\n\n用户补充信息: {context}"

        # ========== 步骤 3: 拼接当前会话历史并调用 LLM API（支持多模态） ==========
        history_messages, history_image_count = build_session_history_messages(user_id, session_id)
        if not history_messages:
            history_messages = build_history_messages(history_items)
            history_image_count = 0

        history_turns_used = sum(1 for msg in history_messages if msg.get('role') == 'user')
        print(f"[Chat API] 🧠 本轮拼接当前会话历史轮数: {history_turns_used}, 历史图片数: {history_image_count}")

        answer = call_qwen_api(
            question,
            context=combined_context,
            image_data_urls=image_data_urls,
            history_messages=history_messages
        )

        # 检查是否是错误信息
        if answer.startswith('❌'):
            return jsonify({'error': answer}), 500

        # ========== 步骤 4: 按会话更新式保存到数据库 ==========
        session_record = Chat.query.filter_by(user_id=user_id, session_id=session_id).order_by(Chat.created_at.asc()).first()

        new_turns = [
            {
                'role': 'user',
                'content': question,
                'file_paths': file_paths,
            },
            {
                'role': 'assistant',
                'content': answer,
            }
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

            old_file_paths = parse_stored_file_paths(session_record.file_path)
            merged_file_paths = old_file_paths + [p for p in file_paths if p not in old_file_paths]
            session_record.file_path = '||'.join(merged_file_paths) if merged_file_paths else None

            chat_record = session_record
        else:
            chat_record = Chat(
                user_id=user_id,
                session_id=session_id,
                question=question,
                answer=answer,
                conversation_json=json.dumps(new_turns, ensure_ascii=False),
                file_path='||'.join(file_paths) if file_paths else None
            )
            db.session.add(chat_record)

        db.session.commit()
        print(f"[Chat API] ✅ 聊天记录已保存，ID: {chat_record.id}")

        # ========== 步骤 5: 返回响应 ==========
        return jsonify({
            'chat_id': chat_record.id,
            'session_id': session_id,
            'question': question,
            'answer': answer,
            'history_turns_used': history_turns_used,
            'history_images_used': history_image_count,
            'has_rag_context': len(rag_context) > 0,
            'has_image': len(image_data_urls) > 0,
            'image_count': len(image_data_urls),
            'created_at': chat_record.created_at.isoformat()
        }), 200

    except Exception as e:
        db.session.rollback()
        error_msg = f"处理失败: {str(e)}"
        print(f"[Chat API] ❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/api/chat/history', methods=['GET'])
@jwt_required()
def get_chat_history():
    """获取当前用户的聊天历史记录"""
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw
        
        requested_session_id = (request.args.get('session_id') or '').strip()
        query = Chat.query.filter_by(user_id=user_id)
        if requested_session_id:
            query = query.filter_by(session_id=requested_session_id)

        # 获取该用户聊天记录，按创建时间倒序排列
        chat_records = query.order_by(Chat.created_at.desc()).all()
        
        # 转换为 JSON 格式
        result = []
        for chat in chat_records:
            result.append({
                'id': chat.id,
                'user_id': chat.user_id,
                'session_id': chat.session_id,
                'question': chat.question,
                'answer': chat.answer,
                'conversation_json': chat.conversation_json,
                'file_path': chat.file_path,
                'created_at': chat.created_at.isoformat() if chat.created_at else None
            })
        
        print(f"[Chat History] ✅ 返回 {len(result)} 条聊天记录 (用户ID: {user_id}, session_id: {requested_session_id or 'ALL'})")
        return jsonify(result), 200
        
    except Exception as e:
        error_msg = f"获取历史记录失败: {str(e)}"
        print(f"[Chat History] ❌ {error_msg}")
        return jsonify({'error': error_msg}), 500


@app.route('/api/chat/history/<int:chat_id>', methods=['DELETE'])
@jwt_required()
def delete_chat_history(chat_id):
    """删除指定的聊天历史记录"""
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw
        
        # 查找聊天记录
        chat_record = Chat.query.filter_by(id=chat_id, user_id=user_id).first()
        
        if not chat_record:
            print(f"[Chat History Delete] ⚠️ 聊天记录不存在或无权限 (ID: {chat_id}, 用户ID: {user_id})")
            return jsonify({'error': '聊天记录不存在或无权限删除'}), 404
        
        # 删除关联的文件（如果存在）
        for stored_path in parse_stored_file_paths(chat_record.file_path):
            if os.path.exists(stored_path):
                try:
                    os.remove(stored_path)
                    print(f"[Chat History Delete] 已删除关联文件: {stored_path}")
                except Exception as e:
                    print(f"[Chat History Delete] ⚠️ 文件删除失败: {e}")
        
        # 删除数据库记录
        db.session.delete(chat_record)
        db.session.commit()
        
        print(f"[Chat History Delete] ✅ 聊天记录已删除 (ID: {chat_id}, 用户ID: {user_id})")
        return jsonify({'message': '聊天记录已删除'}), 200
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"删除历史记录失败: {str(e)}"
        print(f"[Chat History Delete] ❌ {error_msg}")
        return jsonify({'error': error_msg}), 500


@app.route('/api/chat/history/session/<string:session_id>', methods=['DELETE'])
@jwt_required()
def delete_chat_history_by_session(session_id):
    """按会话ID删除聊天历史记录"""
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        chat_records = Chat.query.filter_by(user_id=user_id, session_id=session_id).all()
        if not chat_records:
            print(f"[Chat Session Delete] ⚠️ 会话不存在或无权限 (session_id: {session_id}, 用户ID: {user_id})")
            return jsonify({'error': '会话不存在或无权限删除'}), 404

        all_paths = []
        for chat in chat_records:
            all_paths.extend(parse_stored_file_paths(chat.file_path))

        for stored_path in set(all_paths):
            if os.path.exists(stored_path):
                try:
                    os.remove(stored_path)
                    print(f"[Chat Session Delete] 已删除关联文件: {stored_path}")
                except Exception as e:
                    print(f"[Chat Session Delete] ⚠️ 文件删除失败: {e}")

        Chat.query.filter_by(user_id=user_id, session_id=session_id).delete()
        db.session.commit()

        print(f"[Chat Session Delete] ✅ 会话已删除 (session_id: {session_id}, 用户ID: {user_id})")
        return jsonify({'message': '会话历史已删除'}), 200

    except Exception as e:
        db.session.rollback()
        error_msg = f"删除会话历史失败: {str(e)}"
        print(f"[Chat Session Delete] ❌ {error_msg}")
        return jsonify({'error': error_msg}), 500


@app.route('/api/chat/history', methods=['DELETE'])
@jwt_required()
def delete_all_chat_history():
    """删除当前用户的所有聊天历史记录"""
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw
        
        # 查找该用户的所有聊天记录
        chat_records = Chat.query.filter_by(user_id=user_id).all()
        
        if not chat_records:
            print(f"[Chat History Delete All] ⚠️ 无聊天记录可删除 (用户ID: {user_id})")
            return jsonify({'message': '无聊天记录'}), 200
        
        # 删除关联的文件
        for chat in chat_records:
            for stored_path in parse_stored_file_paths(chat.file_path):
                if os.path.exists(stored_path):
                    try:
                        os.remove(stored_path)
                        print(f"[Chat History Delete All] 已删除文件: {stored_path}")
                    except Exception as e:
                        print(f"[Chat History Delete All] ⚠️ 文件删除失败: {e}")
        
        # 删除所有记录
        Chat.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        
        print(f"[Chat History Delete All] ✅ 已删除 {len(chat_records)} 条聊天记录 (用户ID: {user_id})")
        return jsonify({'message': f'已删除 {len(chat_records)} 条聊天记录'}), 200
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"删除所有历史记录失败: {str(e)}"
        print(f"[Chat History Delete All] ❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

# ==================== 辅助函数 ====================

def generate_answer(question):
    """
    生成回答（这是一个模拟函数，实际应该调用RAG+LLM API）
    """
    # 这里可以集成真实的LLM API，例如OpenAI, Claude等
    return f"这是对您的问题 '{question}' 的回答。（这是一个模拟回答，需要集成真实的LLM API）"

# ==================== 数据库初始化 ====================

@app.route('/api/init-db', methods=['POST'])
def init_db():
    """初始化数据库（仅用于开发）"""
    with app.app_context():
        try:
            db.create_all()
            
            # ========== 添加计算机网络课程视频（来自 B站） ==========
            # 清除旧视频数据，确保总是加载最新的课程信息
            CourseVideo.query.delete()
            db.session.commit()
            print("已清除旧的视频数据")
            
            network_videos = [
                CourseVideo(
                    title='《深入浅出计算机网络》',
                    description='用简单的语言描述复杂的问题，用形象生动的动画演示抽象的概念，用精美的文案给人视觉上的享受。让初学者更容易入门计算机网络。',
                    category='课本配套课程',
                    video_url='https://www.bilibili.com/video/BV1NT411g7n6',
                   
                ),
                CourseVideo(
                    title='王道计算机考研《计算机网络》',
                    description='王道计算机考研课程',
                    category='考研',
                    video_url='https://www.bilibili.com/video/BV19E411D78Q',
                   
                ),
                CourseVideo(
                    title='中科大郑烇、杨坚全套《计算机网络》',
                    description='在介绍计算机网络体系架构的基础上，自上而下、以互联网为例系统地阐述了网络体系结构各层次的主要服务、工作原理、常用技术和协议。',
                    category='高校课程',
                    video_url='https://www.bilibili.com/video/BV1JV411t7ow',
                    
                ),
                CourseVideo(
                    title='《计算机网络，自顶向下方法》配套课程',
                    description='课本配套课程，作者亲授深入讲解计算机网络各个知识点。',
                    category='课本配套课程',
                    video_url='https://www.bilibili.com/video/BV1mb4y1d7K7',
                    
                ),
                CourseVideo(
                    title='谢希仁《计算机网络》课本指定配套微课',
                    description='根据谢希仁《计算机网络》教材内容制作的配套微课程，深入讲解教材核心知识点。',
                    category='课本配套课程',
                    video_url='https://www.bilibili.com/video/BV1LF41177V7',
                    
                ),
                CourseVideo(
                    title='408考研《计算机网络》强化复习',
                    description='针对全国计算机考研408统考的计算机网络强化复习课程，帮助考生突破重难点。',
                    category='考研',
                    video_url='https://www.bilibili.com/video/BV1XHs3zPEuW',
                    
                ),
            ]
            db.session.add_all(network_videos)
            db.session.commit()
            print("✅ 已加载计算机网络课程视频")
            
            # ========== 添加示例课本 ==========
            if Textbook.query.first() is None:
                textbooks = [
                Textbook(
                    title='计算机网络原理',
                    description='系统讲解计算机网络的基本概念和原理',
                    category='基础理论',
                    content='''
# 计算机网络基础知识

## 1. 网络的定义
计算机网络是指将地理位置不同的具有独立功能的多台计算机及其外部设备，通过通信线路连接起来，在网络操作系统、网络管理软件及网络通信协议的管理和协调下，实现资源共享和信息传递的计算机系统。

## 2. 网络的功能
- **资源共享**：硬件资源、软件资源、信息资源
- **数据通信**：高效、可靠的数据传输
- **提高可靠性**：通过冗余路由提高系统可靠性
- **负载均衡**：分散系统负载，提高工作效率

## 3. 网络的分类
根据覆盖范围：
- **局域网(LAN)**：通常在几百米以内
- **城域网(MAN)**：覆盖一个城市
- **广域网(WAN)**：覆盖较大的地理范围

## 4. 协议的重要性
网络协议是计算机之间进行通信的规则和约定，定义了通信的格式、顺序和内容。

常见的协议包括：
- TCP/IP 协议族
- HTTP/HTTPS
- DNS
- SMTP 等

## 5. 网络模型
### OSI 参考模型
分为 7 层，从下到上分别是：
1. 物理层
2. 数据链路层
3. 网络层
4. 传输层
5. 会话层
6. 表示层
7. 应用层

### TCP/IP 模型
更实用的 4 层模型：
1. 网络接口层
2. 网络层
3. 传输层
4. 应用层

## 6. 网络拓扑
- **星形拓扑**：每台计算机都连接到中心计算机
- **环形拓扑**：计算机排成一个环，数据沿环传输
- **总线拓扑**：所有计算机共享同一条传输线路
- **树形拓扑**：多个星形网络通过中继设备连接
- **网状拓扑**：每台计算机都可以与其他多台计算机相连

## 7. IP 地址
IP 地址是互联网上计算机的唯一标识，由 4 个十进制数字组成，范围为 0-255。

### IPv4 地址分类
- **A 类**：1-127（保留为本机地址）
- **B 类**：128-191
- **C 类**：192-223
- **D 类**：224-239（多播地址）
- **E 类**：240-255（保留地址）

### 私有 IP 地址范围
- 10.0.0.0 ~ 10.255.255.255
- 172.16.0.0 ~ 172.31.255.255
- 192.168.0.0 ~ 192.168.255.255

## 8. 子网掩码
用于识别 IP 地址中的网络部分和主机部分。
例如：255.255.255.0 表示前 24 位为网络位，后 8 位为主机位。

## 9. 常见的网络设备
- **交换机**：连接同一网络的计算机
- **路由器**：连接不同的网络，进行数据包转发
- **网关**：不同协议网络间的接口
- **网桥**：连接两个网络段

## 10. 网络管理与安全
- 网络管理：配置、监控和维护网络的正常运行
- 网络安全：防止非法用户的访问和网络病毒的传播

了解这些基础知识是学习计算机网络的第一步，建议深入学习 TCP/IP 协议栈。
                    '''
                ),
                Textbook(
                    title='TCP/IP 协议详解',
                    description='深入学习 TCP/IP 协议族的工作原理',
                    category='协议详解',
                    content='''
# TCP/IP 协议族详解

## 1. TCP/IP 概述
TCP/IP 是互联网的基础协议族，由众多协议组成，实现了计算机的网络通信。

## 2. IP 协议（网络层）
### 功能
- 提供无连接、不可靠的数据报传递
- 进行路由和转发
- 处理数据包的分片和重组

### IP 报头格式
- 版本（4 位）
- 首部长度（4 位）
- 服务类型（8 位）
- 总长度（16 位）
- 标识符、标志和分片偏移（32 位）
- TTL（8 位）
- 协议（8 位）
- 首部检验和（16 位）
- 源 IP 地址和目的 IP 地址（各 32 位）

## 3. TCP 协议（传输层）
### 特点
- 面向连接的协议
- 提供可靠的、有序的数据传输
- 使用流量控制和拥塞控制
- 支持全双工通信

### TCP 三次握手
1. 客户端发送 SYN 报文
2. 服务器回复 SYN-ACK 报文
3. 客户端发送 ACK 报文，连接建立

### TCP 四次挥手
1. 主动方发送 FIN 报文
2. 被动方回复 ACK
3. 被动方发送 FIN 报文
4. 主动方回复 ACK，连接关闭

## 4. UDP 协议（传输层）
### 特点
- 无连接的协议
- 不提供可靠性保证
- 低延迟，适合实时应用
- 支持一对一、一对多、多对多通信

## 5. ICMP 协议
- 互联网控制报文协议
- 用于网络诊断和错误报告
- ping 命令基于 ICMP

## 6. ARP 协议
- 地址解析协议
- 将 IP 地址映射到 MAC 地址
- 在局域网中进行地址解析

## 7. DNS 协议
- 域名系统，将域名转换为 IP 地址
- 使用 UDP 53 端口
- 支持递归和迭代查询

## 8. HTTP 协议
- 超文本传输协议
- 基于 TCP 的应用层协议
- 无状态协议，使用 Cookie 和 Session 实现状态保持

### HTTP 方法
- GET：获取资源
- POST：提交数据
- PUT：更新资源
- DELETE：删除资源
- HEAD：获取资源头信息
- OPTIONS：获取通信选项

### HTTP 状态码
- 1xx：信息状态码
- 2xx：成功状态码
- 3xx：重定向状态码
- 4xx：客户端错误状态码
- 5xx：服务器错误状态码

## 9. HTTPS 协议
- 安全的 HTTP，基于 SSL/TLS
- 提供数据加密和身份验证
- 使用 443 端口

## 10. SMTP、POP3、IMAP 协议
- 邮件传输和接收的相关协议
- SMTP：发送邮件（端口 25）
- POP3：接收邮件（端口 110）
- IMAP：管理邮件（端口 143）

## 学习建议
理解 TCP/IP 协议对于网络编程和网络管理至关重要。建议配合抓包工具（如 Wireshark）进行实际分析。
                    '''
                ),
            ]
            db.session.add_all(textbooks)
            db.session.commit()
            return jsonify({'message': '数据库初始化成功，已添加 8 个计算机网络课程和示例课本'}), 200
        except Exception as e:
            db.session.rollback()
            print(f"❌ 数据库初始化失败: {e}")
            return jsonify({'error': f'初始化失败: {str(e)}'}), 500

# ==================== RAG 管理 API ====================

@app.route('/api/rag/upload-documents', methods=['POST'])
@jwt_required()
def upload_rag_documents():
    """
    上传并处理文档到 RAG 向量数据库
    支持多个文件上传（Word、PDF）
    """
    try:
        if 'files' not in request.files:
            return jsonify({'error': '请上传至少一个文件'}), 400

        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': '未找到上传的文件'}), 400

        # 保存上传的文件
        file_paths = []
        for file in files:
            if file and file.filename:
                # 检查文件格式
                if not file.filename.lower().endswith(('.pdf', '.docx')):
                    continue

                filename = f"rag_{int(datetime.datetime.utcnow().timestamp())}_{secure_filename(file.filename)}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                file_paths.append(file_path)
                print(f"[RAG] 文件已保存: {file_path}")

        if not file_paths:
            return jsonify({'error': '未找到有效的 PDF 或 DOCX 文件'}), 400

        # 添加到 RAG 向量数据库
        rag_manager = get_rag_manager()
        results = rag_manager.add_documents(file_paths, document_source="user_uploaded")

        return jsonify({
            'status': 'success',
            'processed_files': results['processed_files'],
            'total_chunks': results['total_chunks'],
            'errors': results['errors']
        }), 200

    except Exception as e:
        print(f"[RAG] 上传失败: {e}")
        return jsonify({'error': f'处理失败: {str(e)}'}), 500


@app.route('/api/rag/stats', methods=['GET'])
@jwt_required()
def rag_stats():
    """获取 RAG 向量数据库统计信息"""
    try:
        rag_manager = get_rag_manager()
        stats = rag_manager.get_db_stats()
        return jsonify(stats), 200
    except Exception as e:
        print(f"[RAG] 统计信息获取失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500


@app.route('/api/rag/search', methods=['POST'])
@jwt_required()
def rag_search():
    """
    在 RAG 数据库中搜索相关文档
    请求体: {"query": "搜索关键词", "top_k": 5}
    """
    try:
        data = request.get_json()
        if not data or not data.get('query'):
            return jsonify({'error': '查询文本不能为空'}), 400

        query = data.get('query')
        top_k = data.get('top_k', 5)
        mode = data.get('mode', 'hybrid')

        rag_manager = get_rag_manager()
        results = rag_manager.query(query, top_k=top_k, score_threshold=0.3, mode=mode)

        return jsonify({
            'status': 'success',
            'query': query,
            'results_count': len(results),
            'results': results
        }), 200

    except Exception as e:
        print(f"[RAG] 搜索失败: {e}")
        return jsonify({'error': f'搜索失败: {str(e)}'}), 500


@app.route('/api/rag/clear', methods=['POST'])
@jwt_required()
def clear_rag_db():
    """清空 RAG 向量数据库（谨慎使用）"""
    try:
        rag_manager = get_rag_manager()
        result = rag_manager.clear_db()
        return jsonify(result), 200
    except Exception as e:
        print(f"[RAG] 清空失败: {e}")
        return jsonify({'error': f'清空失败: {str(e)}'}), 500


@app.route('/api/rag/init', methods=['POST'])
@jwt_required()
def init_rag_db():
    """
    初始化 RAG 数据库
    根据 backend/documents 目录中的文件进行初始化
    """
    try:
        # 导入初始化脚本
        from pathlib import Path
        documents_dir = Path(__file__).parent / "documents"
        documents_dir.mkdir(exist_ok=True)

        file_paths = list(documents_dir.glob("*.pdf")) + list(documents_dir.glob("*.docx")) + list(documents_dir.glob("*.md"))

        if not file_paths:
            return jsonify({
                'status': 'warning',
                'message': f'documents 目录中未找到文件',
                'documents_dir': str(documents_dir)
            }), 200

        rag_manager = get_rag_manager()
        results = rag_manager.add_documents(
            [str(p) for p in file_paths],
            document_source="builtin"
        )

        return jsonify({
            'status': 'success',
            'processed_files': results['processed_files'],
            'total_chunks': results['total_chunks'],
            'errors': results['errors'],
            'documents_dir': str(documents_dir)
        }), 200

    except Exception as e:
        print(f"[RAG] 初始化失败: {e}")
        return jsonify({'error': f'初始化失败: {str(e)}'}), 500


# ==================== 习题相关 API ====================

@app.route('/api/exercises/generate', methods=['POST'])
@jwt_required()
def generate_exercise():
    """
    生成计算机网络习题 - 采用 RAG + LLM 方式，确保每次生成不同题目
    
    请求体:
    {
        "chapter": "physical_layer|data_link_layer|network_layer|transport_layer|application_layer",
        "question_type": "choice|short_answer",
        "difficulty": "easy|medium|hard",
        "previous_questions": []  # 前端传来的已生成题目ID列表，用于去重
    }
    """
    try:
        data = request.get_json()
        chapter = data.get('chapter', '')
        question_type = data.get('question_type', 'choice')
        difficulty = data.get('difficulty', 'medium')
        previous_questions = data.get('previous_questions', [])  # 已生成题目ID列表
        
        user_id = get_jwt_identity()
        
        # 章节与中文名称的映射
        chapter_mapping = {
            'physical_layer': '物理层',
            'data_link_layer': '数据链路层',
            'network_layer': '网络层',
            'transport_layer': '传输层',
            'application_layer': '应用层'
        }
        
        chapter_name = chapter_mapping.get(chapter, '计算机网络')
        
        print(f"\n[Exercise API] 收到生成题目请求")
        print(f"[Exercise API] 用户ID: {user_id}")
        print(f"[Exercise API] 章节: {chapter_name}, 题型: {question_type}, 难度: {difficulty}")
        
        # ========== 步骤 1: 从 RAG 数据库检索相关知识 ==========
        rag_context = ""
        try:
            rag_manager = get_rag_manager()
            
            # 构建更精确的检索查询
            retrieval_queries = [
                f"{chapter_name}",
                f"{chapter_name}基本概念",
                f"{chapter_name}知识点"
            ]
            
            all_rag_docs = []
            for query in retrieval_queries:
                rag_docs = rag_manager.query(query, top_k=5, score_threshold=0.2)
                all_rag_docs.extend(rag_docs)
            
            if all_rag_docs:
                # 去重：保留来自不同文件的文档，按相似度排序
                unique_docs = {}
                for doc in all_rag_docs:
                    source_file = doc['source']
                    if source_file not in unique_docs or doc['similarity_score'] > unique_docs[source_file]['similarity_score']:
                        unique_docs[source_file] = doc
                
                # 只保留前 5 个不同的文档源
                unique_docs_list = sorted(unique_docs.values(), key=lambda x: x['similarity_score'], reverse=True)[:5]
                
                print(f"[Exercise API] 📚 RAG 检索结果:")
                print(f"[Exercise API] 检索到 {len(unique_docs_list)} 个相关文档")
                
                # 构建 RAG 上下文
                rag_context = f"【{chapter_name}相关知识】\n"
                
                for i, doc in enumerate(unique_docs_list, 1):
                    source = doc['source']
                    similarity = doc['similarity_score']
                    content = doc['content'][:400]
                    
                    print(f"[Exercise API] 文档{i}: {source} (相似度: {similarity:.2%})")
                    
                    rag_context += f"\n【知识点 {i}】\n{content}\n"
                
                print(f"[Exercise API] RAG上下文已构建")
                
            else:
                print(f"[Exercise API] ⚠️ RAG 检索无结果，使用通用模板")
                rag_context = f"【{chapter_name}相关知识背景】\n请根据{chapter_name}的相关知识出题。"
                
        except Exception as e:
            print(f"[Exercise API] ⚠️ RAG 检索异常: {e}")
            import traceback
            traceback.print_exc()
            rag_context = f"【{chapter_name}相关知识背景】\n请根据{chapter_name}的相关知识出题。"
        
        # ========== 步骤 2: 构建动态 Prompt ==========
        # 构建已生成题目的描述（用于提示 LLM 避免重复）
        previous_questions_hint = ""
        if previous_questions:
            previous_questions_hint = f"\n\n【重要】用户已经生成过 {len(previous_questions)} 道题目，你必须生成一道完全不同的题目，包括：\n- 题目问法不同\n- 考查的知识点不同\n- 涉及的场景或例子不同\n确保新题目与所有已生成题目完全不同！"
        
        if question_type == 'choice':
            system_prompt = f"""你是一个专业的计算机网络教学专家，现在需要为学生出一道关于"{chapter_name}"的选择题。

【核心约束】
1. 【章节约束】题目必须严格涉及"{chapter_name}"的知识点，不能超出该章节范围
2. 【题目格式】提供恰好4个选项(A、B、C、D)，只有1个正确答案
3. 【难度控制】根据难度等级"{difficulty}"设计题目：
   - easy: 基础概念题，直接考查定义或基本原理
   - medium: 理解应用题，需要理解和简单推理
   - hard: 综合分析题，需要综合多个知识点或深入分析

【重点：多样性和创意性】
4. 【绝对避免重复】每次必须生成的题目要：
   ✓ 题目问法与之前完全不同
   ✓ 考查的知识点不同（如果有多个知识点，选择不同的组合）
   ✓ 场景和例子不同
   ✓ 选项内容完全不同
   {previous_questions_hint}

5. 【创意出题】为了确保多样性，可以：
   - 考查不同的具体知识点（如果是物理层可以考查光纤、铜线、信噪比、奈奎斯特、香农定理等不同方面）
   - 使用不同的应用场景（实际网络部署、协议分析、故障排查等）
   - 考查不同的难度侧重（基本概念、实际应用、边界情况等）

6. 【题目质量】题目应该：
   - 具有代表性和典型性
   - 避免过于简单或歧义题目
   - 选项应该有一定的迷惑性但不会太容易混淆
   - 正确答案应该是唯一的

【返回格式】严格按照以下 JSON 格式返回：
{{
  "question": "完整的题目文本",
  "options": ["A选项文本", "B选项文本", "C选项文本", "D选项文本"],
  "correct_answer": "A/B/C/D",
  "explanation": "解析说明，说明为什么这是正确答案"
}}

【知识库背景】
请充分利用以下知识库内容来出题：
{rag_context}

"""
            
            user_prompt = f"""请为学生出一道关于{chapter_name}的{difficulty}难度选择题。

要求：
1. 题目内容和问法必须新颖、创意十足
2. 不能重复或接近之前已出过的题目
3. 充分利用知识库中的具体内容来出题
4. 如果有多个知识点可供选择，选择一个未被充分考查过的
5. 确保选项之间有明确的区别，不会让学生产生混淆

请立即生成题目并返回 JSON。"""
            
        else:  # short_answer
            system_prompt = f"""你是一个专业的计算机网络教学专家，现在需要为学生出一道关于"{chapter_name}"的简答题。

【核心约束】
1. 【章节约束】题目必须严格涉及"{chapter_name}"的知识点，不能超出该章节范围
2. 【答案长度】学生答案应该在1-5个句子左右
3. 【难度控制】根据难度等级"{difficulty}"设计题目：
   - easy: 直接考查概念、定义或基本原理，学生可直接从知识点中找到答案
   - medium: 需要学生理解和应用知识点，进行简单推理或对比
   - hard: 需要学生深入理解、综合多个知识点，进行分析和判断

【重点：多样性和创意性】
4. 【绝对避免重复】每次必须生成的题目要：
   ✓ 题目问法与之前完全不同
   ✓ 考查的知识点不同（如果有多个知识点，选择不同的组合）
   ✓ 场景和例子不同
   {previous_questions_hint}

5. 【创意出题】为了确保多样性，可以：
   - 考查不同的具体知识点（如果是物理层可以考查光纤、铜线、信噪比、奈奎斯特、香农定理等不同方面）
   - 使用不同的应用场景（实际网络部署、协议分析、故障排查等）
   - 提出不同类型的问题（"什么是..."、"为什么..."、"怎样..."、"比较..."等）

6. 【题目质量】题目应该：
   - 具有代表性和典型性
   - 启发学生的思考
   - 避免过于宽泛或难以回答的题目
   - 有明确的答案范围

【返回格式】严格按照以下 JSON 格式返回：
{{
  "question": "完整的题目文本，需要学生用文字回答",
  "sample_answer": "标准答案（1-5个句子）",
  "key_points": ["关键知识点1", "关键知识点2", "关键知识点3"],
  "explanation": "解析说明，说明这道题考查的核心内容"
}}

【知识库背景】
请充分利用以下知识库内容来出题：
{rag_context}

"""
            
            user_prompt = f"""请为学生出一道关于{chapter_name}的{difficulty}难度简答题。

要求：
1. 题目内容和问法必须新颖、创意十足
2. 不能重复或接近之前已出过的题目
3. 充分利用知识库中的具体内容来出题
4. 如果有多个知识点可供选择，选择一个未被充分考查过的
5. 题目应该考查学生的理解和应用能力

请立即生成题目并返回 JSON。"""
        
        # ========== 步骤 3: 调用 LLM 生成题目 ==========
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        print(f"[Exercise API] 🤖 调用 LLM 生成题目...")
        print(f"[Exercise API] 已生成题目数: {len(previous_questions)}")
        
        if OPENAI_CLIENT is None:
            raise RuntimeError("LLM 客户端未初始化。请检查后端启动日志或 API 客户端初始化配置。")

        resp = OPENAI_CLIENT.chat.completions.create(
            model="qwen-max",
            messages=messages,
            temperature=1.0,  # 最大化多样性（从 0.95 提升到 1.0）
            max_tokens=1500,  # 增加 token 留白（从 1200 增加到 1500）
            stream=False,
            top_p=0.95  # 提升 nucleus sampling 的范围（从 0.9 提升到 0.95）
        )
        
        # 提取生成的题目
        answer = None
        out = getattr(resp, "output", None) or (resp.get("output") if isinstance(resp, dict) else None)
        if out:
            answer = getattr(out, "text", None) or (out.get("text") if isinstance(out, dict) else None)
        
        if not answer:
            choices = getattr(resp, "choices", None) or (resp.get("choices") if isinstance(resp, dict) else None)
            if choices and len(choices) > 0:
                first = choices[0]
                if isinstance(first, dict):
                    answer = (first.get("message") or {}).get("content") or first.get("text")
                else:
                    answer = getattr(first.message, "content", None) if hasattr(first, "message") else None
        
        if not answer:
            print(f"[Exercise API] ❌ LLM 未返回有效响应")
            return jsonify({'error': '无法生成题目'}), 500
        
        print(f"[Exercise API] ✅ LLM 生成成功，解析响应...")
        
        # ========== 步骤 4: 解析和验证 JSON 格式 ==========
        import json
        exercise_data = None
        
        try:
            import re
            cleaned_answer = re.sub(r'<think>[\s\S]*?</think>', '', answer).strip()
            json_start = cleaned_answer.find('{')
            json_end = cleaned_answer.rfind('}') + 1

            if json_start != -1 and json_end > json_start:
                json_str = cleaned_answer[json_start:json_end]
                exercise_data = json.loads(json_str)
                print(f"[Exercise API] ✅ JSON 解析成功")
            else:
                print(f"[Exercise API] ⚠️ 未找到 JSON 格式，使用原始文本")
                raise json.JSONDecodeError("No JSON found", cleaned_answer, 0)
                
        except json.JSONDecodeError as e:
            print(f"[Exercise API] ⚠️ JSON 解析失败: {e}，使用备用方案")
            exercise_data = {
                'question': answer,
                'type': question_type,
                'difficulty': difficulty,
                'chapter': chapter_name
            }
        
        # ========== 步骤 5: 数据验证和补全 ==========
        if question_type == 'choice':
            if 'options' not in exercise_data or len(exercise_data.get('options', [])) < 4:
                exercise_data['options'] = ['选项A', '选项B', '选项C', '选项D']
            if 'correct_answer' not in exercise_data:
                exercise_data['correct_answer'] = 'A'
        else:
            if 'key_points' not in exercise_data:
                exercise_data['key_points'] = ['关键概念', '核心原理']
            if 'sample_answer' not in exercise_data:
                exercise_data['sample_answer'] = '请参考标准答案'
        
        # 确保所有必需字段存在
        if 'question' not in exercise_data:
            exercise_data['question'] = user_prompt
        if 'explanation' not in exercise_data:
            exercise_data['explanation'] = '详见课程教材'
        
        exercise_data['chapter'] = chapter_name
        exercise_data['difficulty'] = difficulty
        exercise_data['question_type'] = question_type
        
        # 生成题目哈希用于前端去重
        import hashlib
        question_hash = hashlib.md5(exercise_data['question'].encode()).hexdigest()[:8]
        
        print(f"[Exercise API] 📝 题目摘要: {exercise_data['question'][:80]}...")
        print(f"[Exercise API] 题目哈希: {question_hash}")
        print(f"[Exercise API] ✅ 题目生成和验证完成")
        
        # ========== 步骤 6: 返回响应 ==========
        return jsonify({
            'status': 'success',
            'exercise': exercise_data,
            'question_type': question_type,
            'difficulty': difficulty,
            'chapter': chapter_name,
            'has_rag_context': len(rag_context) > 0,
            'question_hash': question_hash  # 返回哈希给前端用于去重
        }), 200
        
    except Exception as e:
        print(f"[Exercise API] ❌ 生成题目失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'生成题目失败: {str(e)}'}), 500


@app.route('/api/exercises/submit', methods=['POST'])
@jwt_required()
def submit_exercise():
    try:
        data = request.get_json()
        question = data.get('question')
        question_type = data.get('question_type')
        user_answer = data.get('user_answer')
        correct_answer = data.get('correct_answer')
        chapter = data.get('chapter', '')
        difficulty = data.get('difficulty', '')
        options = data.get('options')
        explanation = data.get('explanation', '')
        key_points = data.get('key_points')
        sample_answer = data.get('sample_answer', '')

        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        result_data = {}

        if question_type == 'choice':
            is_correct = user_answer.upper() == correct_answer.upper()
            result_data = {
                'status': 'success',
                'is_correct': is_correct,
                'score': 100 if is_correct else 0,
                'feedback': '回答正确！' if is_correct else '回答错误，请再想想',
                'correct_answer': correct_answer,
                'explanation': explanation,
            }
        else:
            try:
                rag_manager = get_rag_manager()
                retrieved_docs = rag_manager.retrieve(question, k=3)
                context = "\n".join([doc['content'][:300] for doc in retrieved_docs])
            except Exception:
                context = ""

            system_prompt = "你是一个专业的计算机网络教学评卷老师。请评判学生的简答题答案是否正确，并给出相应的反馈。回复时不要使用markdown格式。\n\n题目: " + question + "\n\n背景知识: " + context + "\n\n请返回 JSON 格式，包含以下字段:\n- is_correct: true/false\n- score: 0-100 的得分\n- feedback: 评价和建议（中文）\n- key_points: 应该包含的关键点（列表）"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"学生答案: {user_answer}"}
            ]

            if OPENAI_CLIENT is None:
                raise RuntimeError("LLM 客户端未初始化")

            resp = OPENAI_CLIENT.chat.completions.create(
                model="qwen-max",
                messages=messages,
                temperature=0.5,
                max_tokens=500,
                stream=False
            )

            answer = None
            choices = getattr(resp, "choices", None)
            if choices and len(choices) > 0:
                first = choices[0]
                answer = getattr(first.message, "content", None) if hasattr(first, "message") else None

            if not answer:
                return jsonify({'error': '无法评分'}), 500

            import re as _re
            cleaned = _re.sub(r'<think>[\s\S]*?</think>', '', answer).strip()
            try:
                js = cleaned[cleaned.find('{'):cleaned.rfind('}') + 1]
                result_data = json.loads(js) if js else {}
            except Exception:
                result_data = {'feedback': cleaned, 'score': 0, 'is_correct': False}

            result_data.setdefault('is_correct', False)
            result_data.setdefault('score', 0)
            result_data.setdefault('feedback', '')
            result_data['status'] = 'success'
            if sample_answer:
                result_data['correct_answer'] = sample_answer

        is_correct = result_data.get('is_correct', False)
        score = result_data.get('score', 100 if is_correct else 0)

        record = ExerciseRecord(
            user_id=user_id,
            chapter=chapter,
            question_type=question_type,
            difficulty=difficulty,
            question=question,
            options_json=json.dumps(options, ensure_ascii=False) if options else None,
            correct_answer=correct_answer or sample_answer,
            user_answer=user_answer,
            is_correct=is_correct,
            score=score,
            feedback=result_data.get('feedback', ''),
            explanation=explanation or result_data.get('explanation', ''),
            key_points_json=json.dumps(key_points or result_data.get('key_points'), ensure_ascii=False) if (key_points or result_data.get('key_points')) else None,
        )
        db.session.add(record)
        db.session.commit()
        result_data['record_id'] = record.id

        return jsonify(result_data), 200

    except Exception as e:
        db.session.rollback()
        print(f"[Exercise] 提交失败: {e}")
        return jsonify({'error': f'提交失败: {str(e)}'}), 500


@app.route('/api/exercises/history', methods=['GET'])
@jwt_required()
def get_exercise_history():
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        query = ExerciseRecord.query.filter_by(user_id=user_id)

        chapter = request.args.get('chapter')
        if chapter:
            query = query.filter_by(chapter=chapter)

        question_type = request.args.get('question_type')
        if question_type:
            query = query.filter_by(question_type=question_type)

        is_correct = request.args.get('is_correct')
        if is_correct is not None and is_correct != '':
            query = query.filter_by(is_correct=is_correct.lower() == 'true')

        records = query.order_by(ExerciseRecord.created_at.desc()).all()
        return jsonify([r.to_dict() for r in records]), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/exercises/stats', methods=['GET'])
@jwt_required()
def get_exercise_stats():
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        records = ExerciseRecord.query.filter_by(user_id=user_id).all()
        total = len(records)
        correct = sum(1 for r in records if r.is_correct)
        by_chapter = {}
        for r in records:
            ch = r.chapter or '未分类'
            if ch not in by_chapter:
                by_chapter[ch] = {'total': 0, 'correct': 0}
            by_chapter[ch]['total'] += 1
            if r.is_correct:
                by_chapter[ch]['correct'] += 1

        return jsonify({
            'total': total,
            'correct': correct,
            'wrong': total - correct,
            'accuracy': round(correct / total * 100, 1) if total > 0 else 0,
            'by_chapter': by_chapter,
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/exercises/history/<int:record_id>', methods=['DELETE'])
@jwt_required()
def delete_exercise_record(record_id):
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        record = ExerciseRecord.query.filter_by(id=record_id, user_id=user_id).first()
        if not record:
            return jsonify({'error': '记录不存在'}), 404

        db.session.delete(record)
        db.session.commit()
        return jsonify({'message': '已删除'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/exercises/history', methods=['DELETE'])
@jwt_required()
def clear_exercise_history():
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        ExerciseRecord.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        return jsonify({'message': '已清空所有练习记录'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==================== 笔记 API ====================

@app.route('/api/notes', methods=['POST'])
@jwt_required()
def create_note():
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        data = request.get_json()
        if not data or not data.get('title') or not data.get('content'):
            return jsonify({'error': '标题和内容不能为空'}), 400

        note = Note(
            user_id=user_id,
            textbook_title=data.get('textbook_title', ''),
            title=data['title'],
            content=data['content'],
            page_number=data.get('page_number'),
        )
        db.session.add(note)
        db.session.commit()
        return jsonify(note.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/notes', methods=['GET'])
@jwt_required()
def get_notes():
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        query = Note.query.filter_by(user_id=user_id)

        textbook = request.args.get('textbook_title')
        if textbook:
            query = query.filter_by(textbook_title=textbook)

        keyword = request.args.get('keyword')
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(
                db.or_(Note.title.like(like), Note.content.like(like))
            )

        notes = query.order_by(Note.created_at.desc()).all()
        return jsonify([n.to_dict() for n in notes]), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/notes/<int:note_id>', methods=['PUT'])
@jwt_required()
def update_note(note_id):
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        note = Note.query.filter_by(id=note_id, user_id=user_id).first()
        if not note:
            return jsonify({'error': '笔记不存在'}), 404

        data = request.get_json()
        if data.get('title'):
            note.title = data['title']
        if data.get('content'):
            note.content = data['content']
        if 'page_number' in data:
            note.page_number = data['page_number']

        db.session.commit()
        return jsonify(note.to_dict()), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
@jwt_required()
def delete_note(note_id):
    try:
        user_id_raw = get_jwt_identity()
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = user_id_raw

        note = Note.query.filter_by(id=note_id, user_id=user_id).first()
        if not note:
            return jsonify({'error': '笔记不存在'}), 404

        db.session.delete(note)
        db.session.commit()
        return jsonify({'message': '已删除'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': '资源不存在'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': '服务器内部错误'}), 500

if __name__ == '__main__':
    from pathlib import Path

    with app.app_context():
        db.create_all()

        # 启动时自动清除旧课程数据并加载新的课程视频
        try:
            print("[STARTUP] 正在清除旧的课程视频数据...")
            CourseVideo.query.delete()
            db.session.commit()
            print("✅ [STARTUP] 旧课程视频数据已清除")
            
            # 加载新的课程视频
            network_videos = [
                CourseVideo(
                    title='《深入浅出计算机网络》',
                    description='用简单的语言描述复杂的问题，用形象生动的动画演示抽象的概念，用精美的文案给人视觉上的享受。让初学者更容易入门计算机网络。',
                    category='课本配套课程',
                    video_url='https://www.bilibili.com/video/BV1NT411g7n6',
                ),
                CourseVideo(
                    title='王道计算机考研《计算机网络》',
                    description='王道计算机考研课程',
                    category='考研',
                    video_url='https://www.bilibili.com/video/BV19E411D78Q',
                ),
                CourseVideo(
                    title='中科大郑烇、杨坚全套《计算机网络》',
                    description='在介绍计算机网络体系架构的基础上，自上而下、以互联网为例系统地阐述了网络体系结构各层次的主要服务、工作原理、常用技术和协议。',
                    category='高校课程',
                    video_url='https://www.bilibili.com/video/BV1JV411t7ow',
                ),
                CourseVideo(
                    title='《计算机网络，自顶向下方法》配套课程',
                    description='课本配套课程，作者亲授深入讲解计算机网络各个知识点。',
                    category='课本配套课程',
                    video_url='https://www.bilibili.com/video/BV1mb4y1d7K7',
                ),
                CourseVideo(
                    title='谢希仁《计算机网络》课本指定配套微课',
                    description='根据谢希仁《计算机网络》教材内容制作的配套微课程，深入讲解教材核心知识点。',
                    category='课本配套课程',
                    video_url='https://www.bilibili.com/video/BV1LF41177V7',
                ),
                CourseVideo(
                    title='408考研《计算机网络》强化复习',
                    description='针对全国计算机考研408统考的计算机网络强化复习课程，帮助考生突破重难点。',
                    category='考研',
                    video_url='https://www.bilibili.com/video/BV1XHs3zPEuW',
                ),
            ]
            db.session.add_all(network_videos)
            db.session.commit()
            print("✅ [STARTUP] 已加载6个新的计算机网络课程视频")
            
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ [STARTUP] 课程视频加载失败: {e}")

        # 启动时自动初始化 RAG 向量数据库（优先 Data，其次 documents）
        try:
            data_dir = Path(os.path.join(os.path.dirname(__file__), '..', 'Data'))

            if not data_dir.exists():
                print(f"[RAG INIT] Data 目录不存在，尝试使用 documents 目录")
                data_dir = Path(__file__).parent / "documents"

            files = []
            if data_dir.exists():
                files = [str(p) for p in (list(data_dir.glob("*.pdf")) +
                                          list(data_dir.glob("*.docx")) +
                                          list(data_dir.glob("*.md")))]

            if files:
                try:
                    rag_manager = get_rag_manager()
                    print(f"[RAG INIT] 初始化知识库，加载 {len(files)} 个文件 from {data_dir}")
                    results = rag_manager.add_documents(files, document_source="builtin_startup")
                    print(f"[RAG INIT] 处理结果: {results}")
                except Exception as e:
                    print(f"[RAG INIT] 初始化失败: {e}")
            else:
                print(f"[RAG INIT] 未找到 Data/documents 中的文件，跳过初始化: {data_dir}")

        except Exception as e:
            print(f"[RAG INIT] 启动时初始化异常: {e}")

    app.run(debug=True, host='0.0.0.0', port=8000)