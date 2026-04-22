#!/bin/bash

echo "🚀 启动 E-Learning 系统..."
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 确保 Node 18 和 brew 在 PATH 中
export PATH="/opt/homebrew/opt/node@18/bin:/opt/homebrew/bin:$PATH"

# 基于脚本位置的动态路径
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"

# 直接使用 conda test 环境的 Python 绝对路径
PY="/opt/homebrew/Caskroom/miniconda/base/envs/test/bin/python"
if [ ! -x "$PY" ]; then
    echo -e "${YELLOW}⚠️ conda test 环境的 Python 不存在，尝试系统 Python${NC}"
    PY="$(command -v python3 || command -v python)"
fi

# =============== 后端启动 ===============
echo -e "${BLUE}1️⃣  启动后端服务...${NC}"

cd "$BACKEND_DIR" || { echo "无法切换到 $BACKEND_DIR"; exit 1; }

# 清除旧进程
if lsof -i :8000 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  端口 8000 已被占用，尝试清除...${NC}"
    lsof -i :8000 | grep -v COMMAND | awk '{print $2}' | xargs kill -9 2>/dev/null || true
    sleep 1
fi

echo "使用 Python: $PY"

# 初始化（如果没有 vector_db）
if [ ! -d "vector_db" ]; then
    echo -e "${YELLOW}[后端] 首次运行，初始化数据库...${NC}"
    mkdir -p documents vector_db uploads
    "$PY" init_rag_db.py
fi

# 启动后端
"$PY" app.py > /tmp/backend.log 2>&1 &
BACKEND_PID=$!

echo -e "${GREEN}✅ 后端已启动 (PID: $BACKEND_PID)${NC}"
echo "   访问地址: http://localhost:8000/api"
echo "   日志文件: /tmp/backend.log"
echo ""

# 等待后端启动
sleep 4

# =============== 前端启动 ===============
echo -e "${BLUE}2️⃣  启动前端服务...${NC}"

cd "$FRONTEND_DIR" || { echo "无法切换到 $FRONTEND_DIR"; exit 1; }

# 若前端缺少依赖，先自动安装（避免在错误目录运行 npm）
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}[前端] 未检测到 node_modules，执行 npm install...${NC}"
    npm install || { echo "npm install 失败，请手动检查"; }
fi

# 清除旧进程
if lsof -i :3000 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  端口 3000 已被占用，尝试清除...${NC}"
    lsof -i :3000 | grep -v COMMAND | awk '{print $2}' | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# 启动前端（后台运行）
npm start > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!

echo -e "${GREEN}✅ 前端已启动 (PID: $FRONTEND_PID)${NC}"
echo "   访问地址: http://localhost:3000"
echo "   日志文件: /tmp/frontend.log"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 系统启动完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}📱 快速开始:${NC}"
echo "   1. 打开浏览器: http://localhost:3000"
echo "   2. 注册账户或登录"
echo "   3. 进入'知识学习'页面"
echo "   4. 点击'课程视频'标签查看视频"
echo "   5. 点击'开始学习'在 B站观看视频"
echo ""
echo -e "${BLUE}📝 监控日志:${NC}"
echo "   后端: tail -f /tmp/backend.log"
echo "   前端: tail -f /tmp/frontend.log"
echo ""
echo -e "${BLUE}🛑 停止服务:${NC}"
echo "   kill $BACKEND_PID  # 停止后端"
echo "   kill $FRONTEND_PID # 停止前端"
echo ""
echo -e "${GREEN}🎉 E-Learning 系统已启动！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "📋 运行中的服务:"
echo "  • 后端: http://localhost:8000 (PID: $BACKEND_PID)"
echo "  • 前端: http://localhost:3000 (PID: $FRONTEND_PID)"
echo ""
echo "📊 日志文件:"
echo "  • 后端日志: /tmp/backend.log"
echo "  • 前端日志: /tmp/frontend.log"
echo ""
echo "⏹️  停止服务:"
echo "  kill $BACKEND_PID    # 停止后端"
echo "  kill $FRONTEND_PID   # 停止前端"
echo ""
echo "查看日志:"
echo "  tail -f /tmp/backend.log"
echo "  tail -f /tmp/frontend.log"
echo ""

# 保持脚本运行
wait
