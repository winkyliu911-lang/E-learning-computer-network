#!/bin/bash

echo "🚀 E-Learning 升级版启动脚本"
echo "================================"
echo ""

PROJECT_DIR="/Users/winky/Desktop/e-learning"

# 检查后端环境
echo "1️⃣  检查后端环境..."
cd "$PROJECT_DIR/backend"

if [ ! -d "venv" ]; then
    echo "❌ 虚拟环境不存在，请先创建："
    echo "   python3.11 -m venv venv"
    exit 1
fi

source venv/bin/activate

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "⚠️  .env 文件不存在，创建默认配置..."
    cat > .env << 'EOF'
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key-2024
DATABASE_URL=sqlite:///elearning.db
DASHSCOPE_API_KEY=sk-your-api-key-here
JWT_SECRET_KEY=your-jwt-secret-key
EOF
    echo "📝 请编辑 .env 文件，设置 DASHSCOPE_API_KEY"
fi

# 初始化数据库
echo ""
echo "2️⃣  初始化 RAG 数据库..."
if [ -d "vector_db" ] && [ ! -z "$(ls -A vector_db)" ]; then
    echo "✅ RAG 数据库已存在"
else
    echo "🔧 创建新的 RAG 数据库..."
    mkdir -p documents vector_db uploads
    python3 init_rag_db.py
fi

# 启动后端
echo ""
echo "3️⃣  启动后端服务..."
echo "📍 后端运行在: http://localhost:8000"
echo "💡 按 Ctrl+C 停止后端"
echo ""

python3 app.py &
BACKEND_PID=$!

sleep 2

# 检查后端是否启动成功
if ! ps -p $BACKEND_PID > /dev/null; then
    echo "❌ 后端启动失败！"
    exit 1
fi

echo "✅ 后端已启动 (PID: $BACKEND_PID)"

# 启动前端
echo ""
echo "4️⃣  启动前端服务..."
cd "$PROJECT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    echo "📦 安装 NPM 依赖..."
    npm install
fi

echo "📍 前端运行在: http://localhost:3000"
echo "💡 按 Ctrl+C 停止前端"
echo ""

npm start &
FRONTEND_PID=$!

sleep 3

# 显示信息
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║  ✨ E-Learning 启动完成！                ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "🌐 访问地址:"
echo "   • 前端: http://localhost:3000"
echo "   • 后端: http://localhost:8000"
echo ""
echo "📚 新功能:"
echo "   • 知识学习中心（左侧视频 + 右侧教科书）"
echo "   • 习题练习（选择题 + 简答题 + AI 评分）"
echo "   • AI ChatBot"
echo ""
echo "🛑 停止服务:"
echo "   kill $BACKEND_PID    # 停止后端"
echo "   kill $FRONTEND_PID   # 停止前端"
echo ""
echo "📖 查看详情: cat UPGRADE_SUMMARY.md"
echo ""

# 等待
wait
