#!/bin/bash

# NYU Dating Copilot 重启脚本
# 使用方法: ./restart.sh

echo "🔄 重启 NYU Dating Copilot..."

# 停止现有服务
./stop.sh

# 等待一下确保进程完全停止
sleep 2

# 启动服务
./start.sh