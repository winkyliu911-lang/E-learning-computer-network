from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import bcrypt

db = SQLAlchemy()

# 用户模型
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    chats = db.relationship('Chat', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """设置密码哈希"""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        """验证密码"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat()
        }

# 课程视频模型
class CourseVideo(db.Model):
    __tablename__ = 'course_videos'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100), nullable=False)
    video_url = db.Column(db.String(500), nullable=False)
    duration = db.Column(db.Integer)  # 秒
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'video_url': self.video_url,
            'duration': self.duration,
            'created_at': self.created_at.isoformat()
        }

# 课本模型
class Textbook(db.Model):
    __tablename__ = 'textbooks'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'content': self.content,
            'created_at': self.created_at.isoformat()
        }

# 聊天消息模型
class Chat(db.Model):
    __tablename__ = 'chats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(db.String(64), index=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text)
    conversation_json = db.Column(db.Text)
    file_path = db.Column(db.String(500))  # 上传文件的路径
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'question': self.question,
            'answer': self.answer,
            'conversation_json': self.conversation_json,
            'file_path': self.file_path,
            'created_at': self.created_at.isoformat()
        }


class ExerciseRecord(db.Model):
    __tablename__ = 'exercise_records'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    chapter = db.Column(db.String(100))
    question_type = db.Column(db.String(20))
    difficulty = db.Column(db.String(20))
    question = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.Text)
    correct_answer = db.Column(db.Text)
    user_answer = db.Column(db.Text)
    is_correct = db.Column(db.Boolean, default=False)
    score = db.Column(db.Integer, default=0)
    feedback = db.Column(db.Text)
    explanation = db.Column(db.Text)
    key_points_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'user_id': self.user_id,
            'chapter': self.chapter,
            'question_type': self.question_type,
            'difficulty': self.difficulty,
            'question': self.question,
            'options': json.loads(self.options_json) if self.options_json else None,
            'correct_answer': self.correct_answer,
            'user_answer': self.user_answer,
            'is_correct': self.is_correct,
            'score': self.score,
            'feedback': self.feedback,
            'explanation': self.explanation,
            'key_points': json.loads(self.key_points_json) if self.key_points_json else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Note(db.Model):
    __tablename__ = 'notes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    textbook_title = db.Column(db.String(255))
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    page_number = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'textbook_title': self.textbook_title,
            'title': self.title,
            'content': self.content,
            'page_number': self.page_number,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
