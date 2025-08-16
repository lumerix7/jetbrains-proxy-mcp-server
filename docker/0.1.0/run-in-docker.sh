#!/usr/bin/env bash
set -x

docker stop jetbrains-proxy-mcp-server
docker rm jetbrains-proxy-mcp-server

docker run -d --name jetbrains-proxy-mcp-server \
  --privileged --restart unless-stopped \
  -e SIMP_LOGGER_LOG_LEVEL=DEBUG \
  -e SIMP_LOGGER_LOG_CONSOLE_ENABLED=True \
  -e JETBRAINS_PROXY_MCP_SERVER_TRANSPORT=sse \
  -e JETBRAINS_PROXY_MCP_SERVER_SSE_DEBUG_ENABLED=True \
  -e JETBRAINS_PROXY_MCP_SERVER_CONFIG="/root/config.yaml" \
  -v "$(pwd)/config.yaml:/root/config.yaml" \
  --network host \
  jetbrains-proxy-mcp-server:0.1.0 \
  || exit 1
