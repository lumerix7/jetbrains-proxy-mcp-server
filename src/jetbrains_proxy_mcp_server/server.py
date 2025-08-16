"""server.py: This file contains the server code for the MCP server."""

from typing import Any, Coroutine

import anyio.to_thread
from mcp.server import Server
from mcp.types import Tool, ContentBlock, TextContent

from .logger import get_logger
from .properties import MCPServerProperties
from .schema.exceptions import ToolError
from .service import JetbrainsMCPServerProxy


def serve(properties_path: str | None = None) -> None:
    log = get_logger()

    properties = MCPServerProperties()
    properties.load(properties_path)
    log.info(f"Successfully load properties from {properties_path}.")

    proxy = JetbrainsMCPServerProxy(properties=properties.jetbrains_mcp_server)
    proxy.bootstrap()

    server = Server(properties.server_name)

    def run_on_proxy(coro: Coroutine) -> Any:
        """Run a coroutine on the proxy's event loop and wait for the result."""

        import asyncio

        # This is a bit of a hack to access _loop. A public method would be better.
        # But for now, this is fine.
        loop = getattr(proxy, "_loop", None)
        if not loop or not loop.is_running():
            log.error(
                "Proxy event loop is not running. Please ensure the proxy is started before calling this function.")
            raise RuntimeError(
                "Proxy event loop is not running. Please ensure the proxy is started before calling this function")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(properties.timeout)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        try:
            result = await anyio.to_thread.run_sync(run_on_proxy, proxy.list_tools())
        except BaseException as e:
            import traceback
            log.error(f"Exception listing tools: {e}:\n{traceback.format_exc()}")
            raise
        return result.tools

    @server.call_tool()
    async def call_tool(name: str, args: dict) -> list[ContentBlock]:
        try:
            result = await anyio.to_thread.run_sync(run_on_proxy, proxy.call_tool(name, args))

            if result.isError:
                message = ""
                try:
                    blocks = result.content or []
                    parts: list[str] = []
                    for block in blocks:
                        if isinstance(block, TextContent) and block.text:
                            parts.append(str(block.text))
                    message = " ".join(p.strip() for p in parts if p and p.strip()).strip()
                except BaseException as e:
                    log.warning(f"Failed to parse tool error message: {e}. Returning a generic error message instead.")
                if not message:
                    message = "Error calling tool. Please check the server logs for more details."
                raise ToolError(message=message, code=500)

            return result.content
        except BaseException as e:
            import traceback
            log.error(f"Exception calling tool {name} with args {args}: {e}:\n{traceback.format_exc()}")
            raise

    # Start the server
    options = server.create_initialization_options()

    if properties.transport == "sse":
        log.info(f"Starting server with SSE transport on {properties.sse_bind_host}:{properties.sse_port}... "
                 f"debug = {properties.sse_debug_enabled}, transport endpoint = {properties.sse_transport_endpoint}.")

        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        import uvicorn

        async def handle_sse(request):
            async with sse.connect_sse(
                    request.scope, request.receive, request._send
            ) as streams:
                await server.run(streams[0], streams[1], options)

        sse = SseServerTransport(properties.sse_transport_endpoint)

        routes = [
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]

        starlette_app = Starlette(debug=properties.sse_debug_enabled, routes=routes)
        uvicorn.run(starlette_app, host=properties.sse_bind_host, port=properties.sse_port)
    else:
        import os

        if os.getenv("SIMP_LOGGER_LOG_CONSOLE_ENABLED", "True").lower() != "false":
            log.error("SIMP_LOGGER_LOG_CONSOLE_ENABLED must be set to False to use stdio transport.")
            raise ToolError(message="SIMP_LOGGER_LOG_CONSOLE_ENABLED must be set to False to use stdio transport",
                            code=400)

        log.info(f"Starting server with stdio transport... "
                 f"debug = {properties.sse_debug_enabled}, transport endpoint = {properties.sse_transport_endpoint}.")

        from mcp import stdio_server

        async def run_stdio_server():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, options)

        import asyncio

        asyncio.run(run_stdio_server())
