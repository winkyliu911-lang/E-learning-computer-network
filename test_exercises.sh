#!/bin/bash

# 习题生成功能测试脚本
# 用法: chmod +x test_exercises.sh && ./test_exercises.sh

API_BASE="http://localhost:8000/api"
TOKEN="" # 你需要替换为实际的token或通过登录获取

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   习题生成功能测试脚本${NC}"
echo -e "${BLUE}========================================${NC}\n"

# 获取token（通过登录）
echo -e "${YELLOW}正在登录获取token...${NC}"
LOGIN_RESPONSE=$(curl -s -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "test", "password": "test"}')

TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo -e "${RED}获取token失败${NC}"
  echo "响应: $LOGIN_RESPONSE"
  exit 1
fi

echo -e "${GREEN}✅ 登录成功，获得token${NC}\n"

# 测试1: 物理层 - 选择题 - 简单难度
echo -e "${BLUE}测试1: 物理层 - 选择题 - 简单难度${NC}"
RESPONSE=$(curl -s -X POST "$API_BASE/exercises/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "chapter": "physical_layer",
    "question_type": "choice",
    "difficulty": "easy"
  }')

echo "响应:"
echo "$RESPONSE" | python3 -m json.tool
echo ""

# 测试2: 数据链路层 - 简答题 - 中等难度
echo -e "${BLUE}测试2: 数据链路层 - 简答题 - 中等难度${NC}"
RESPONSE=$(curl -s -X POST "$API_BASE/exercises/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "chapter": "data_link_layer",
    "question_type": "short_answer",
    "difficulty": "medium"
  }')

echo "响应:"
echo "$RESPONSE" | python3 -m json.tool
echo ""

# 测试3: 网络层 - 选择题 - 困难难度
echo -e "${BLUE}测试3: 网络层 - 选择题 - 困难难度${NC}"
RESPONSE=$(curl -s -X POST "$API_BASE/exercises/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "chapter": "network_layer",
    "question_type": "choice",
    "difficulty": "hard"
  }')

echo "响应:"
echo "$RESPONSE" | python3 -m json.tool
echo ""

# 测试4: 传输层 - 简答题 - 困难难度
echo -e "${BLUE}测试4: 传输层 - 简答题 - 困难难度${NC}"
RESPONSE=$(curl -s -X POST "$API_BASE/exercises/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "chapter": "transport_layer",
    "question_type": "short_answer",
    "difficulty": "hard"
  }')

echo "响应:"
echo "$RESPONSE" | python3 -m json.tool
echo ""

# 测试5: 应用层 - 选择题 - 中等难度
echo -e "${BLUE}测试5: 应用层 - 选择题 - 中等难度${NC}"
RESPONSE=$(curl -s -X POST "$API_BASE/exercises/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "chapter": "application_layer",
    "question_type": "choice",
    "difficulty": "medium"
  }')

echo "响应:"
echo "$RESPONSE" | python3 -m json.tool
echo ""

# 测试6: 物理层题目多样性测试 (连续生成3题)
echo -e "${BLUE}测试6: 物理层 - 题目多样性测试（连续生成3题）${NC}"
for i in 1 2 3; do
  echo -e "${YELLOW}第 $i 题:${NC}"
  RESPONSE=$(curl -s -X POST "$API_BASE/exercises/generate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{
      "chapter": "physical_layer",
      "question_type": "choice",
      "difficulty": "medium"
    }')
  
  QUESTION=$(echo "$RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('exercise', {}).get('question', 'N/A'))")
  echo "题目: $QUESTION"
  echo ""
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   所有测试完成！${NC}"
echo -e "${GREEN}========================================${NC}"
