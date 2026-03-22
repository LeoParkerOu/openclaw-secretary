#!/bin/bash
# start_gateway.sh — 启动 openclaw gateway
# 设置 NO_PROXY 绕过飞书域名，防止本地代理导致 WebSocket 重定向循环

export NO_PROXY=open.feishu.cn,lark-office.feishu.cn,feishu.cn
export no_proxy=open.feishu.cn,lark-office.feishu.cn,feishu.cn

NODE=/Users/hih/.nvm/versions/node/v22.19.0/bin/node
OPENCLAW=/Users/hih/.nvm/versions/node/v22.19.0/bin/openclaw

# 停止已有实例
pkill -f openclaw-gateway 2>/dev/null
sleep 1

nohup "$NODE" "$OPENCLAW" gateway > /tmp/openclaw-gateway.log 2>&1 &
echo "Gateway started (PID $!)"
echo "Log: tail -f /tmp/openclaw-gateway.log"
