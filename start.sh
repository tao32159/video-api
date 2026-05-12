#!/bin/bash
# Render 部署入口脚本

echo "🚀 开始安装依赖..."
pip install -r requirements.txt

echo "📁 创建临时目录..."
mkdir -p temp

echo "🚀 启动服务..."
uvicorn api.main:app --host 0.0.0.0 --port $PORT
