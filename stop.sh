#!/bin/bash

# NYU Dating Copilot 停止脚本
# 使用方法: ./stop.sh

echo "🛑 停止 NYU Dating Copilot..."

# 查找并停止所有相关进程
if lsof -Pi :9000 -sTCP:LISTEN -t >/dev/null ; then
    echo "🔍 发现运行中的服务，正在停止..."
    lsof -ti:9000 | xargs kill -9 2>/dev/null || true
    echo "✅ 服务已停止"
else
    echo "ℹ️  没有发现运行中的服务"
fi

# 也尝试通过进程名停止
pkill -f "python.*app.py" 2>/dev/null || true

echo "🏁 完成"