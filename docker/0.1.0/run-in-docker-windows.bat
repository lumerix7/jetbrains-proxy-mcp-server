docker stop jetbrains-mcp-knowledge-mcp-server-windows
docker rm jetbrains-proxy-mcp-server-windows

docker run -d --name jetbrains-proxy-mcp-server-windows ^
  --privileged --restart unless-stopped ^
  -e SIMP_LOGGER_LOG_LEVEL=DEBUG ^
  -e SIMP_LOGGER_LOG_CONSOLE_ENABLED=True ^
  -e JETBRAINS_PROXY_MCP_SERVER_TRANSPORT=sse ^
  -e JETBRAINS_PROXY_MCP_SERVER_SSE_DEBUG_ENABLED=True ^
  -e JETBRAINS_PROXY_MCP_SERVER_CONFIG="/root/config.yaml" ^
  -v "%~dp0config-windows.yaml:/root/config.yaml" ^
  --network host ^
  jetbrains-proxy-mcp-server:0.1.0
pause
