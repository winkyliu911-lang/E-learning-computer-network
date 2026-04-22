# E-Learning Computer Network

一个基于 Flask + React 的计算机网络在线学习平台，集成了 AI 聊天机器人、智能习题练习、RAG 知识库检索、课本阅读与笔记等功能。

## 功能概览

- **AI 聊天机器人**：基于通义千问大模型，支持上传 PDF、Word、图片进行多模态问答，结合 RAG 知识库提供专业回答
- **知识学习**：在线观看 B 站课程视频，阅读 PDF 教科书，支持分屏做笔记
- **智能习题练习**：AI 自动生成选择题和简答题，支持章节筛选、难度选择，简答题由 AI 评分反馈
- **练习记录**：完整的答题历史记录，统计正确率，按章节分析薄弱环节
- **笔记系统**：阅读课本时实时记录笔记，支持搜索、编辑、按教科书筛选
- **混合 RAG 检索**：BM25 关键词搜索 + 向量语义搜索 + RRF 融合排序，提升检索准确率

## 技术栈

### 后端
- Python 3.9 / Flask
- SQLAlchemy + SQLite
- ChromaDB 向量数据库
- sentence-transformers 文本嵌入
- rank_bm25 + jieba 中文分词
- 通义千问 API（OpenAI 兼容接口）

### 前端
- React 18
- Ant Design 5 组件库
- Axios HTTP 客户端

## 项目结构

```
├── backend/
│   ├── app.py              # Flask 主应用，所有 API 端点
│   ├── models.py           # 数据库模型（User, Chat, ExerciseRecord, Note）
│   ├── rag_manager.py      # RAG 管理器（混合检索：BM25 + 向量 + RRF）
│   ├── file_extractor.py   # 文件转换（PDF/Word 转图片）
│   ├── config.py           # 应用配置
│   └── requirements.txt    # Python 依赖
├── frontend/
│   ├── src/
│   │   ├── api.js          # API 请求封装
│   │   ├── components/
│   │   │   ├── ChatBot.js          # AI 聊天界面
│   │   │   ├── KnowledgeLearning.js # 知识学习（视频、课本、笔记）
│   │   │   ├── ExercisePractice.js  # 习题练习
│   │   │   ├── ExerciseHistory.js   # 练习记录
│   │   │   ├── ChatHistory.js       # 聊天历史
│   │   │   └── CourseVideos.js      # 课程视频
│   │   └── pages/
│   │       ├── AuthPage.js      # 登录注册
│   │       └── DashboardPage.js # 主界面布局
│   └── public/             # PDF 教科书文件
├── Data/                   # RAG 知识库文档（PDF、Word、Markdown）
└── start.sh                # 一键启动脚本
```

## 快速开始

### 环境要求
- Python 3.9+
- Node.js 18+
- Conda（推荐）

### 安装步骤

1. 克隆项目
```bash
git clone https://github.com/winkyliu911-lang/e-learning.git
cd e-learning
```

2. 安装后端依赖
```bash
conda create -n test python=3.9 -y
conda activate test
cd backend
pip install -r requirements.txt
pip install rank_bm25 jieba docx2txt httpx==0.27.2
```

3. 安装前端依赖
```bash
cd frontend
npm install
```

4. 一键启动
```bash
bash start.sh
```

启动后访问 http://localhost:3000

### 手动启动

后端（端口 8000）：
```bash
conda activate test
cd backend
python app.py
```

前端（端口 3000）：
```bash
cd frontend
npm start
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/auth/register | POST | 用户注册 |
| /api/auth/login | POST | 用户登录 |
| /api/chat | POST | AI 对话（支持文件上传） |
| /api/chat/history | GET | 获取聊天历史 |
| /api/exercises/generate | POST | AI 生成习题 |
| /api/exercises/submit | POST | 提交答案并评分 |
| /api/exercises/history | GET | 练习记录查询 |
| /api/exercises/stats | GET | 练习统计数据 |
| /api/notes | GET/POST | 笔记查询/创建 |
| /api/notes/:id | PUT/DELETE | 笔记编辑/删除 |
| /api/videos | GET | 获取课程视频列表 |
| /api/rag/search | POST | RAG 知识库搜索 |

## 截图

### 主要功能页面
- 知识学习中心：课程视频、教科书阅读、分屏笔记
- AI ChatBot：多模态问答，支持上传文件
- 习题练习：AI 生成题目，自动评分
- 练习记录：答题历史、正确率统计、章节分析
