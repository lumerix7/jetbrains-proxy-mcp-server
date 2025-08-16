"""properties/JetbrainsMCPServer.py"""

from typing import Any

from pydantic import BaseModel


class JetbrainsMCPServer(BaseModel):
    # Name of the MCP server, required.
    name: str = "jetbrains-mcp-server"

    # Environment variables to run the MCP server for stdio type, defaults to None.
    env: dict[str, str] = None
    # Text encoding used when sending/receiving messages to the server, defaults to utf-8.
    encoding: str = "utf-8"
    # Text encoding error handler. "strict", "ignore" or "replace", defaults to "strict".
    # See https://docs.python.org/3/library/codecs.html#codec-base-classes for explanations of possible values
    encoding_error_handler: str = "strict"

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

    debug_enabled: bool = True

    proxy_path_type: str = "wsl"
    jetbrains_path_type: str = "windows"
