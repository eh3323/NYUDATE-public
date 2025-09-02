#!/bin/bash

# NYU Dating Copilot 启动脚本
# 使用方法: ./start.sh

echo "🚀 启动 NYU Dating Copilot..."

# 检查虚拟环境是否存在
if [ ! -d ".venv" ]; then
    echo "❌ 错误: 未找到虚拟环境 .venv"
    echo "请先运行: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 检查是否有进程在使用9000端口
if lsof -Pi :9000 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  端口 9000 已被占用，正在停止现有进程..."
    lsof -ti:9000 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# 激活虚拟环境并启动应用
echo "🔧 激活虚拟环境..."
source .venv/bin/activate

echo "📦 检查依赖..."
if ! python -c "import flask" 2>/dev/null; then
    echo "❌ 缺少依赖，请运行: pip install -r requirements.txt"
    exit 1
fi

echo "🌐 启动 Flask 应用..."
echo "📱 访问地址: http://localhost:9000"
echo "🛑 按 Ctrl+C 停止服务"
echo ""

# 启动应用
python app.py