# E-Learning——Computer Network

AI-Powered E-Learning Platform for Computer Networking Education — integrating multimodal LLM, hybrid RAG retrieval, and intelligent assessment.

## Features

- **AI Chatbot**: Multimodal Q&A powered by Qwen-VL-Max, supports uploading images/PDF/DOCX, RAG-augmented responses with source attribution
- **Hybrid RAG System**: BM25 keyword search + vector semantic search + Reciprocal Rank Fusion (RRF), with query expansion and LRU caching
- **Knowledge Base**: 17 built-in files (PDF/DOCX/Markdown) covering all networking layers; user uploads automatically indexed
- **Smart Exercises**: AI-generated multiple choice & short answer questions across 5 chapters and 3 difficulty levels
- **Auto Grading**: LLM-based evaluation (0-100) with feedback, key points, and explanations
- **Knowledge Learning**: Bilibili video courses, PDF textbook reader with split-screen note-taking
- **Note System**: Create, search, and manage notes linked to textbooks with page numbers
- **Practice Analytics**: Per-chapter accuracy tracking, visual statistics dashboard

## Tech Stack

### Backend
- **Framework**: Flask 2.3 with Blueprint modular architecture (7 route modules)
- **Database**: SQLAlchemy + SQLite (6 tables), ChromaDB vector DB (HNSW, cosine)
- **Auth**: Flask-JWT-Extended (dual token: access + refresh), bcrypt password hashing
- **RAG**: BM25Okapi + Sentence-Transformers (MiniLM-L12-v2, 384-dim) + RRF fusion
- **NLP**: jieba Chinese tokenization, query expansion (20+ CN-EN term mappings)
- **LLM**: Qwen-VL-Max (multimodal chat) & Qwen-Max (exercise gen/grading) via DashScope API
- **File Processing**: PyMuPDF (PDF→images), python-docx + Pillow (DOCX→images)

### Frontend
- **Framework**: React 18 with React Router v6
- **UI**: Ant Design 5 component library
- **HTTP**: Axios with JWT auto-refresh interceptors

## Project Structure

```
├── backend/
│   ├── app.py                # Flask entry (~120 lines), Blueprint registration
│   ├── config.py             # App configuration (env vars)
│   ├── models.py             # SQLAlchemy models (User, Chat, ExerciseRecord, Note, etc.)
│   ├── rag_manager.py        # Hybrid RAG engine (BM25 + Vector + RRF)
│   ├── file_extractor.py     # PDF/DOCX to image conversion
│   ├── seed_data.py          # Course data seeding from JSON
│   ├── routes/
│   │   ├── auth.py           # Authentication (register, login, refresh)
│   │   ├── chat.py           # AI chat with RAG + multimodal
│   │   ├── exercises.py      # Exercise generation & grading
│   │   ├── rag.py            # RAG knowledge base management
│   │   ├── videos.py         # Course video CRUD
│   │   ├── textbooks.py      # Textbook CRUD + file serving
│   │   └── notes.py          # Note CRUD
│   ├── services/
│   │   ├── llm_service.py    # LLM client (Qwen API via OpenAI compatible)
│   │   └── logging_config.py # Logging setup
│   ├── data/
│   │   └── courses.json      # Course video seed data
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.js            # Routes + RequireAuth
│   │   ├── api.js            # Axios API modules with JWT interceptors
│   │   ├── index.js          # BrowserRouter entry
│   │   ├── components/
│   │   │   ├── ChatBot.js
│   │   │   ├── KnowledgeLearning.js
│   │   │   ├── ExercisePractice.js
│   │   │   ├── ExerciseHistory.js
│   │   │   ├── ChatHistory.js
│   │   │   └── CourseVideos.js
│   │   └── pages/
│   │       ├── AuthPage.js
│   │       └── DashboardPage.js
│   └── public/               # PDF textbook files
├── Data/                     # RAG knowledge base (17 files: PDF, DOCX, Markdown)
├── .env.example              # Environment variable template
└── start.sh                  # Backend startup script
```

## Quick Start

### Requirements
- Python 3.9+
- Node.js 18+

### Installation

1. Clone
```bash
git clone https://github.com/winkyliu911-lang/E-learning-computer-network.git
cd E-learning-computer-network
```

2. Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install rank_bm25 jieba docx2txt httpx
```

3. Frontend
```bash
cd frontend
npm install
```

4. Configure (optional)
```bash
cp .env.example .env
# Edit .env with your API keys
```

### Run

Backend (port 8000):
```bash
cd backend
source venv/bin/activate
python3 app.py
```

Frontend (port 3000):
```bash
cd frontend
npm start
```

Or use the startup script:
```bash
bash backend/start.sh  # starts backend
cd frontend && npm start  # starts frontend in another terminal
```

Visit http://localhost:3000

## RAG Pipeline

```
Document Ingestion:
  Data/ (17 files) + User Uploads
  → LangChain Loaders (PDF/DOCX/MD)
  → RecursiveCharacterTextSplitter (1000 chars, 200 overlap)
  → Dual indexing: ChromaDB (384-dim vectors) + BM25 (jieba tokenized)

Query Time:
  User Query → Query Expansion (CN-EN term mapping)
  → Parallel retrieval:
    Path A: Sentence-Transformers → ChromaDB cosine search → Top-K
    Path B: jieba tokenize → BM25Okapi scoring → Top-K
  → RRF Fusion: score = Σ 1/(60 + rank)
  → Deduplicate by source → Top-3 contexts → LLM
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/auth/register | POST | User registration |
| /api/auth/login | POST | User login |
| /api/auth/refresh | POST | Refresh access token |
| /api/chat | POST | AI chat (supports file upload) |
| /api/chat/history | GET/DELETE | Chat history management |
| /api/exercises/generate | POST | AI exercise generation |
| /api/exercises/submit | POST | Submit answer & auto-grade |
| /api/exercises/history | GET/DELETE | Exercise records |
| /api/exercises/stats | GET | Practice statistics |
| /api/notes | GET/POST | Notes query/create |
| /api/notes/:id | PUT/DELETE | Notes edit/delete |
| /api/videos | GET | Course video list |
| /api/rag/search | POST | RAG knowledge base search |
| /api/rag/stats | GET | RAG database statistics |
