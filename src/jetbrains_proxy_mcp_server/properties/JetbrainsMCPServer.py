"""properties/JetbrainsMCPServer.py"""

from typing import Any

from pydantic import BaseModel


class JetbrainsMCPServer(BaseModel):
    # Name of the MCP server, required.
    name: str = "jetbrains-mcp-server"

    # URL of the MCP server for sse type, default is None.
    url: str = "http://127.0.0.1:64342/sse"
    # Headers to send with the request for sse type, defaults to None.
    headers: dict[str, Any] = None
    # Timeout for the remote MCP server request, in seconds, defaults to 35.0 seconds.
    timeout: float = 35.0
    # Timeout for the SSE read, defaults to 60 * 5 seconds.
    sse_read_timeout: float = 60 * 5

    start_timeout: float = 120.0
    stop_timeout: float = 30.0
    max_attempts: int = 5
    initial_backoff: float = 1.0
    max_backoff: float = 60.0
    backoff_multiplier: float = 3.0

    # Path type for the client, default is "wsl", available options are "wsl", "windows_git_bash" and "windows".
    client_path_type: str = "wsl"
    server_path_type: str = "windows"

    debug_enabled: bool = True
