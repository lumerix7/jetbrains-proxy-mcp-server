import asyncio
import threading
import time
from asyncio import TimeoutError as TE
from enum import Enum, auto
from typing import Any, Callable, Coroutine

import mcp
from mcp import ListToolsResult
from mcp.types import CallToolResult, TextContent

from ..logger import get_logger
from ..paths import convert_path
from ..properties import JetbrainsMCPServer
from ..schema import ToolError
from ..utils import execute, get, AttemptHookArgs


class SS(Enum):
    """Server Status Enum to represent the current state of the MCP server."""

    STOPPED = auto()
    STARTING = auto()
    STARTED = auto()
    STOPPING = auto()


class MCPServer:
    """MCPServer class to hold the transport context, session and tools."""

    transport_context: Any
    session: mcp.ClientSession

    def __init__(self, transport_context: Any = None, session: mcp.ClientSession = None):
        self.transport_context = transport_context
        self.session = session


class JetbrainsMCPServerProxy:
    supported_tools = [
        # "create_new_file", # Note, this tool is not working correctly: stuck or not responding success
        "get_all_open_file_paths",
        "get_file_problems",
        "get_file_text_by_path",
        "get_project_dependencies",
        "get_project_modules",
        "get_project_problems",
        "list_directory_tree",
        "reformat_file",
        "rename_refactoring",
        "replace_text_in_file",
        "search_in_files_by_regex",
        "search_in_files_by_text",
    ]

    properties: JetbrainsMCPServer
    server: MCPServer | None = None
    status: SS = SS.STOPPED

    tool_handlers: dict[str, Callable[[float, dict[str, Any]], Coroutine[Any, Any, CallToolResult]]]

    _lock: asyncio.Lock
    _status_changed: asyncio.Condition
    _loop: asyncio.AbstractEventLoop | None = None
    _loop_thread: threading.Thread | None = None

    def __init__(self, properties: JetbrainsMCPServer):
        self.properties = properties
        self._lock = asyncio.Lock()
        self._status_changed = asyncio.Condition(self._lock)

        if not properties or not properties.url or not properties.url.strip():
            log = get_logger()
            log.error("Jetbrains MCP Server URL is not configured.")
            raise ValueError("Jetbrains MCP Server URL is not configured")

        self.tool_handlers = {
            # "create_new_file": self._do_create_new_file,
            "get_all_open_file_paths": self._do_get_all_open_file_paths,
            "get_file_problems": self._do_get_file_problems,
            "get_file_text_by_path": self._do_get_file_text_by_path,
            "list_directory_tree": self._do_list_directory_tree,
            "reformat_file": self._do_reformat_file,
            "rename_refactoring": self._do_rename_refactoring,
            "replace_text_in_file": self._do_replace_text_in_file,
            "search_in_files_by_regex": self._do_search_in_files_by_regex,
            "search_in_files_by_text": self._do_search_in_files_by_text,
        }

    def bootstrap(self):
        """Start the proxy in a standalone thread."""

        if self._loop_thread is not None and self._loop_thread.is_alive():
            return

        log = get_logger()
        name = self.properties.name
        log.info(f"Bootstrapping proxy loop for {name} in a standalone thread...")

        def loop_thread():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()
            except BaseException as e:
                import traceback
                log.error(f"Exception proxy loop thread: {e}:\n{traceback.format_exc()}")
            finally:
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)
                log.info(f"Stopped proxy loop thread for {name}.")

        self._loop_thread = threading.Thread(target=loop_thread, name=f"proxy-{name}", daemon=True)
        self._loop_thread.start()

        try:
            log.info(f"Successfully bootstrapped proxy loop for {name}.")
        except BaseException as e:
            import traceback
            log.error(f"Exception bootstrapping proxy loop for {name}: {e}:\n{traceback.format_exc()}")
            raise

    async def start(self):
        await self._start(self.properties.start_timeout)

    async def _start(self, timeout: float):
        log = get_logger()
        deadline = time.monotonic() + timeout

        async with self._lock:
            if self.status == SS.STARTED:
                log.info(f"Server {self.properties.name} is already started.")
                return

            while self.status in (SS.STARTING, SS.STOPPING):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TE(f"Timeout waiting for server {self.properties.name} to become stable before starting. "
                             f"Current status: {self.status.name}")
                try:
                    await asyncio.wait_for(self._status_changed.wait(), timeout=remaining)
                except TE:
                    raise TE(f"Timeout waiting for server {self.properties.name} to become stable before starting. "
                             f"Current status: {self.status.name}")

            if self.status == SS.STARTED:
                log.info(f"Server {self.properties.name} is already started.")
                return

            if self.status != SS.STOPPED:
                raise RuntimeError(f"Unexcepted status {self.status.name} after waiting server {self.properties.name}")

            self.status = SS.STARTING

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            async with self._lock:
                self.status = SS.STOPPED
                self._status_changed.notify_all()
            raise TE(f"Not enough time left to start server {self.properties.name}")

        try:
            await execute(
                self._do_start,
                retryer_timeout=remaining,
                retryer_max_attempts=self.properties.max_attempts,
                retryer_initial_backoff=self.properties.initial_backoff,
                retryer_max_backoff=self.properties.max_backoff,
                retryer_backoff_multiplier=self.properties.backoff_multiplier,
            )

            async with self._lock:
                self.status = SS.STARTED
                self._status_changed.notify_all()
                log.info(f"Successfully started server {self.properties.name}.")

        except BaseException as e:
            import traceback
            log.error(f"Exception starting server {self.properties.name}: {e}:\n{traceback.format_exc()}")
            async with self._lock:
                self.status = SS.STOPPED
                self._status_changed.notify_all()
            raise

    async def _do_start(self):
        from mcp.client.sse import sse_client

        log = get_logger()
        name = self.properties.name

        transport_context: Any = None
        session: mcp.ClientSession | None = None

        try:
            transport_context = sse_client(
                url=self.properties.url,
                headers=self.properties.headers,
                timeout=self.properties.timeout,
                sse_read_timeout=self.properties.sse_read_timeout,
            )
            streams = await transport_context.__aenter__()

            log.info(f"Ready streams for sse server: {name}, creating and initializing session...")

            session = mcp.ClientSession(*streams)
            await session.__aenter__()
            await session.initialize()

            self.server = MCPServer(transport_context=transport_context, session=session)

            log.info(
                f"Successfully started sse server: {name}, url = {self.properties.url}, "
                f"headers = {self.properties.headers}, "
                f"timeout = {self.properties.timeout}, sse_read_timeout = {self.properties.sse_read_timeout}.")

        except BaseException as e:
            import traceback
            log.error(f"Exception starting sse server: {name}: {e}:\n{traceback.format_exc()}")
            await self._do_stop0(timeout=self.properties.stop_timeout, transport_context=transport_context,
                                 session=session)
            raise e

    async def _ensure_started(self, timeout: float):
        """Ensure the server is started, if not, start it."""

        async with self._lock:
            if self.status == SS.STARTED:
                return

        await self._start(timeout)

    async def restart(self):
        await self._restart(self.properties.start_timeout)

    async def _restart(self, timeout: float):
        log = get_logger()
        deadline = time.monotonic() + timeout

        await self._stop(timeout=timeout)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.error(f"Timeout before starting again after stopping server {self.properties.name}.")
            raise TE(f"Timeout before starting again after stopping server {self.properties.name}.")

        await self._start(remaining)

    async def _restart_on_error(self, args: AttemptHookArgs):
        log = get_logger()
        if args.error:
            if isinstance(args.error, (TimeoutError, TE)):
                log.warning(f"Timeout error on attempt {args.attempt}, not restarting server {self.properties.name}.")
                return
            if isinstance(args.error, ToolError) and args.error.code == 408:
                log.warning(f"Timeout tool error on attempt {args.attempt}, "
                            f"not restarting server {self.properties.name}.")
                return

        log.warning(f"Restarting server {self.properties.name} on attempt {args.attempt} due to error: {args.error}")
        try:
            remaining = args.deadline - time.monotonic()
            if remaining <= 0:
                log.warning(f"Not enough time to restart server {self.properties.name}. Skipping restart.")
                return

            await self._restart(remaining)
            log.info(f"Successfully restarted server {self.properties.name} on attempt {args.attempt}.")
        except BaseException as e:
            import traceback
            log.warning(f"Exception restarting server {self.properties.name} (Ignored): {e}\n{traceback.format_exc()}")

    async def stop(self):
        """Stop the server no exceptions are raised."""
        await self._stop(timeout=self.properties.stop_timeout)

    async def _stop(self, timeout: float):
        log = get_logger()
        deadline = time.monotonic() + timeout

        async with self._lock:
            if self.status == SS.STOPPED:
                log.info(f"Server {self.properties.name} is already stopped.")
                return

            while self.status in (SS.STARTING, SS.STOPPING):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    log.warning(f"Timeout waiting for server {self.properties.name} to become stable before stopping. "
                                f"Current status: {self.status.name}")
                    return
                try:
                    await asyncio.wait_for(self._status_changed.wait(), timeout=remaining)
                except TE:
                    log.warning(
                        f"Timeout waiting for server {self.properties.name} to become stable before stopping. "
                        f"Current status: {self.status.name}")
                    return

            if self.status == SS.STOPPED:
                log.info(f"Server {self.properties.name} is already stopped.")
                return

            if self.status != SS.STARTED:
                log.warning(f"Cannot stop server {self.properties.name} because its status is {self.status.name}")
                return

            self.status = SS.STOPPING
            self._status_changed.notify_all()

        try:
            if self.server is None:
                log.warning(f"Inconsistent state: server status is STARTED but server object is None. "
                            f"Server {self.properties.name} is not running.")
            else:
                transport_context = self.server.transport_context
                session = self.server.session
                remaining = max(1.0, deadline - time.monotonic())
                await self._do_stop0(timeout=remaining, transport_context=transport_context, session=session)
        except BaseException as e:
            log.warning(f"Exception stopping sse server: {self.properties.name}: {e}. Ignoring...")
        finally:
            self.server = None
            async with self._lock:
                self.status = SS.STOPPED
                self._status_changed.notify_all()
            log.info(f"Stopped server {self.properties.name}.")

    async def _do_stop0(self, timeout: float,
                        transport_context: Any | None = None, session: mcp.ClientSession | None = None):
        try:
            deadline = timeout + time.monotonic()

            await execute(
                self._do_stop, deadline=deadline, transport_context=transport_context, session=session,
                retryer_timeout=timeout,
                retryer_max_attempts=self.properties.max_attempts,
                retryer_initial_backoff=self.properties.initial_backoff,
                retryer_max_backoff=self.properties.max_backoff,
                retryer_backoff_multiplier=self.properties.backoff_multiplier,
            )
        except BaseException as e:
            log = get_logger()
            log.warning(f"Exception stopping sse server: {self.properties.name}: {e}. Ignoring...")

    async def _do_stop(self, deadline: float,
                       transport_context: Any | None = None, session: mcp.ClientSession | None = None,
                       ):
        log = get_logger()
        timeout = max(1.0, deadline - time.monotonic())

        if session is not None:
            try:
                if transport_context is not None:
                    timeout = timeout / 3.0 * 2.0
                await asyncio.wait_for(session.__aexit__(None, None, None), timeout=timeout)
            except TE:
                log.error(f"Timeout closing session of {self.properties.name} after {timeout}s. Ignoring.")
            except BaseException as e:
                log.error(f"Exception closing session of {self.properties.name}: {e}. Ignoring.")

        if transport_context is not None:
            try:
                timeout = max(1.0, deadline - time.monotonic())
                await asyncio.wait_for(transport_context.__aexit__(None, None, None), timeout=timeout)
            except TE:
                log.error(
                    f"Timeout closing transport_context of {self.properties.name} after {timeout}s. Ignoring.")
            except BaseException as e:
                log.error(f"Exception closing transport_context of {self.properties.name}: {e}. Ignoring.")

    async def list_tools(self) -> ListToolsResult:
        log = get_logger()
        timeout = self.properties.timeout
        deadline = time.monotonic() + timeout

        await self._ensure_started(timeout)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.error(f"Timeout before listing tools after {remaining}s.")
            raise TE(f"Timeout before listing tools after {remaining}s")

        try:
            return await get(
                self._do_list_tools, deadline=deadline,
                retryer_timeout=remaining,
                retryer_max_attempts=self.properties.max_attempts,
                retryer_initial_backoff=self.properties.initial_backoff,
                retryer_max_backoff=self.properties.max_backoff,
                retryer_backoff_multiplier=self.properties.backoff_multiplier,
                retryer_attempt_hook=self._restart_on_error,
            )
        except BaseException as e:
            import traceback
            log.error(f"Exception listing tools on {self.properties.name}: {e}.\n{traceback.format_exc()}")
            await self.stop()
            raise

    async def _do_list_tools(self, deadline: float) -> ListToolsResult:
        log = get_logger()
        debug = self.properties.debug_enabled
        name = self.properties.name
        timeout = max(1.0, deadline - time.monotonic())

        try:
            if debug:
                log.debug(f"Listing tools on {name} with timeout {timeout}s...")
            result = await asyncio.wait_for(self.server.session.list_tools(), timeout=timeout)
        except TE:
            import traceback
            log.error(
                f"Timeout calling list_tools on {name} after {timeout}s:\n{traceback.format_exc()}")
            await self.stop()
            raise ToolError(message="Timeout calling list_tools after {timeout}s.", code=408)
        except BaseException as e:
            import traceback
            log.error(f"Exception calling list_tools on {name}: {e}.\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling list_tools on {name}: {e}", code=500)

        if result.tools:
            unsupported = {t.name for t in result.tools if t.name not in self.supported_tools}
            if unsupported:
                for name in unsupported:
                    log.warning(f"Tool `{name}` is not supported by MCP server proxy. Discarding.")
                result.tools = [t for t in result.tools if t.name in self.supported_tools]
                result.tools.sort(key=lambda t: t.name)

        if debug:
            log.debug(f"List tools result: {result.model_dump_json(indent=2)}.")

        return result

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """Dispatch to a specialized handler defined in tool_handlers if available, else fallback to _do_call_tool."""

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        timeout = self.properties.timeout
        deadline = time.monotonic() + timeout

        await self._ensure_started(timeout)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.error(f"Timeout before calling tool {name} after {remaining}s.")
            raise TE(f"Timeout before calling tool {name} after {remaining}s")

        handler = self.tool_handlers.get(name)
        if handler:
            if debug:
                log.debug(f"Dispatching to specialized handler for tool `{name}` with arguments: {arguments}")
            return await get(
                handler, deadline, arguments,
                retryer_timeout=remaining,
                retryer_max_attempts=self.properties.max_attempts,
                retryer_initial_backoff=self.properties.initial_backoff,
                retryer_max_backoff=self.properties.max_backoff,
                retryer_backoff_multiplier=self.properties.backoff_multiplier,
                retryer_attempt_hook=self._restart_on_error,
            )

        if debug:
            log.debug(f"No specialized handler for tool `{name}`, falling back to generic do_call_tool. "
                      f"Arguments: {arguments}")

        return await get(
            self._do_call_tool, deadline=deadline, name=name, arguments=arguments,
            retryer_timeout=remaining,
            retryer_max_attempts=self.properties.max_attempts,
            retryer_initial_backoff=self.properties.initial_backoff,
            retryer_max_backoff=self.properties.max_backoff,
            retryer_backoff_multiplier=self.properties.backoff_multiplier,
            retryer_attempt_hook=self._restart_on_error,
        )

    async def _do_call_tool(self, deadline: float, name: str, arguments: dict[str, Any]) -> CallToolResult:
        log = get_logger()
        debug = self.properties.debug_enabled

        timeout = max(1.0, deadline - time.monotonic())

        try:
            response = await asyncio.wait_for(
                self.server.session.call_tool(name=name, arguments=arguments),
                timeout=timeout
            )
        except TE:
            import traceback
            log.error(f"Timeout calling {name} on {self.properties.name} after {timeout}s.\n{traceback.format_exc()}")
            raise ToolError(message=f"Timeout calling {name} after {timeout}s.", code=408)
        except BaseException as e:
            import traceback
            log.error(f"Exception calling {name} on {self.properties.name}: {e}.\n{traceback.format_exc()}")
            await self.stop()
            raise ToolError(message=f"Exception calling {name}: {e}", code=500)

        if debug:
            log.debug(f"Call tool response: {response.model_dump_json(indent=2)}.")
        return response

    # UNUSED
    async def _do_create_new_file(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "create_new_file",
              "description": "Creates a new file at the specified path within the project directory and optionally populates it with text if provided.\nUse this tool to generate new files in your project structure.\nNote: Creates any necessary parent directories automatically",
              "inputSchema": {
                "properties": {
                  "pathInProject": {
                    "type": "string",
                    "description": "Path where the file should be created relative to the project root"
                  },
                  "text": {
                    "type": "string",
                    "description": "Content to write into the new file"
                  }
                },
                "required": [
                  "pathInProject"
                ],
                "type": "object"
              }
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if 'pathInProject' not in arguments:
            log.error("Missing required argument: pathInProject")
            raise ToolError(message="Missing required argument: pathInProject", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            path = arguments.get('pathInProject', None)
            if path and isinstance(path, str) and path.strip():
                arguments['pathInProject'] = convert_path(path=path, from_type=server_path_type,
                                                          to_type=client_path_type)

        try:
            if debug:
                log.debug(f"Calling create_new_file with arguments: {arguments}.")

            response = await self._do_call_tool(deadline=deadline, name="create_new_file", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling create_new_file: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling create_new_file: {e}", code=500)

        if debug:
            log.debug(f"create_new_file response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_get_all_open_file_paths(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "get_all_open_file_paths",
              "description": "Returns active editor's and other open editors' file paths relative to the project root.\n\nUse this tool to explore current open editors.",
              "inputSchema": {
                "properties": {},
                "required": [],
                "type": "object"
              }
            }

            Response example:
            {
              "meta": {},
              "content": [
                {
                  "type": "text",
                  "text": {
                    "activeFilePath": "src\\jetbrains_proxy_mcp_server\\service\\JetbrainsMCPServerProxy.py",
                    "openFiles": [
                      "src\\jetbrains_proxy_mcp_server\\service\\JetbrainsMCPServerProxy.py",
                      "src\\jetbrains_proxy_mcp_server\\properties\\MCPServerProperties.py"
                    ]
                  }
                }
              ],
              "isError": false
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        try:
            if debug:
                log.debug(f"Calling get_all_open_file_paths with arguments: {arguments}.")

            response = await self._do_call_tool(deadline=deadline, name="get_all_open_file_paths",
                                                arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling get_all_open_file_paths: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling get_all_open_file_paths: {e}", code=500)

        if debug:
            log.debug(f"Original get_all_open_file_paths response: {response.model_dump_json(indent=2)}.")

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if not path_mismatch or response.isError or not response.content:
            return response

        for c in response.content:
            if isinstance(c, TextContent):
                import json
                text_dict = json.loads(c.text)

                afp = text_dict.get('activeFilePath', None)
                if afp and isinstance(afp, str) and afp.strip():
                    text_dict['activeFilePath'] = convert_path(path=afp, from_type=server_path_type,
                                                               to_type=client_path_type)

                ofs = text_dict.get('openFiles', None)
                if isinstance(ofs, list):
                    converted = []
                    for p in ofs:
                        if p and isinstance(p, str) and p.strip():
                            converted.append(convert_path(path=p, from_type=server_path_type,
                                                          to_type=client_path_type))
                    text_dict['openFiles'] = converted

                c.text = json.dumps(text_dict)

        if debug:
            log.debug(f"Converted get_all_open_file_paths response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_get_file_problems(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "get_file_problems",
              "description": "Analyzes the specified file for errors and warnings using IntelliJ's inspections.\nUse this tool to identify coding issues, syntax errors, and other problems in a specific file.\nReturns a list of problems found in the file, including severity, description, and location information.\nNote: Only analyzes files within the project directory.\nNote: Lines and Columns are 1-based.",
              "inputSchema": {
                "properties": {
                  "filePath": {
                    "type": "string",
                    "description": "Path relative to the project root"
                  },
                  "errorsOnly": {
                    "type": "boolean",
                    "description": "Whether to include only errors or include both errors and warnings"
                  },
                  "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds"
                  }
                },
                "required": [
                  "filePath"
                ],
                "type": "object"
              }
            }

            Response example:
            {
              "meta": {},
              "content": [
                {
                  "type": "text",
                  "text": {
                    "filePath": "src\\jetbrains_proxy_mcp_server\\service\\JetbrainsMCPServerProxy.py",
                    "errors": []
                  }
                }
              ],
              "isError": false
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        if 'filePath' not in arguments:
            log.error("Missing required argument: filePath")
            raise ToolError(message="Missing required argument: filePath", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            path = arguments.get('filePath', None)
            if path and isinstance(path, str) and path.strip():
                arguments['filePath'] = convert_path(path=path, from_type=client_path_type, to_type=server_path_type)

        try:
            if debug:
                log.debug(f"Calling get_file_problems with arguments: {arguments}. Need convert: {path_mismatch}")
            response = await self._do_call_tool(deadline=deadline, name="get_file_problems", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling get_file_problems: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling get_file_problems: {e}", code=500)

        if debug:
            log.debug(f"Original get_file_problems response: {response.model_dump_json(indent=2)}.")

        if not path_mismatch or response.isError or not response.content:
            return response

        try:
            for c in response.content:
                if isinstance(c, TextContent):
                    import json
                    text_dict = json.loads(c.text)
                    fp = text_dict.get('filePath', None)
                    if fp and isinstance(fp, str) and fp.strip():
                        text_dict['filePath'] = convert_path(path=fp, from_type=server_path_type,
                                                             to_type=client_path_type)
                    c.text = json.dumps(text_dict)
        except BaseException as e:
            import traceback
            log.warning(f"Exception converting filePath in get_file_problems response: {e}. "
                        f"Response content: {response.content}. Ignoring conversion:\n{traceback.format_exc()}")

        if debug:
            log.debug(f"Converted get_file_problems response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_get_file_text_by_path(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "get_file_text_by_path",
              "description": "        Retrieves the text content of a file using its path relative to project root.\n        Use this tool to read file contents when you have the file's project-relative path.\n        In the case of binary files, the tool returns an error.\n        If the file is too large, the text will be truncated with '<<<...content truncated...>>>' marker and in according to the `truncateMode` parameter.",
              "inputSchema": {
                "properties": {
                  "pathInProject": {
                    "type": "string",
                    "description": "Path relative to the project root"
                  },
                  "truncateMode": {
                    "enum": [
                      "START",
                      "MIDDLE",
                      "END",
                      "NONE"
                    ],
                    "description": "How to truncate the text: from the start, in the middle, at the end, or don't truncate at all"
                  },
                  "maxLinesCount": {
                    "type": "integer",
                    "description": "Max number of lines to return. Truncation will be performed depending on truncateMode."
                  }
                },
                "required": [
                  "pathInProject"
                ],
                "type": "object"
              }
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        if 'pathInProject' not in arguments:
            log.error("Missing required argument: pathInProject")
            raise ToolError(message="Missing required argument: pathInProject", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            path = arguments.get('pathInProject', None)
            if path and isinstance(path, str) and path.strip():
                arguments['pathInProject'] = convert_path(path=path, from_type=client_path_type,
                                                          to_type=server_path_type)

        try:
            if debug:
                log.debug(f"Calling get_file_text_by_path with arguments: {arguments}. Need convert: {path_mismatch}")
            response = await self._do_call_tool(deadline=deadline, name="get_file_text_by_path", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling get_file_text_by_path: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling get_file_text_by_path: {e}", code=500)

        if debug:
            log.debug(f"Original get_file_text_by_path response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_list_directory_tree(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "list_directory_tree",
              "description": "Provides a tree representation of the specified directory in the pseudo graphic format like `tree` utility does.\nUse this tool to explore the contents of a directory or the whole project.\nYou MUST prefer this tool over listing directories via command line utilities like `ls` or `dir`.",
              "inputSchema": {
                "properties": {
                  "directoryPath": {
                    "type": "string",
                    "description": "Path relative to the project root"
                  },
                  "maxDepth": {
                    "type": "integer",
                    "description": "Maximum recursion depth"
                  },
                  "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds"
                  }
                },
                "required": [
                  "directoryPath"
                ],
                "type": "object"
              }
            }

            Response example:
            {
              "content": [
                {
                  "type": "text",
                  "text": {
                    "traversedDirectory": "mcp",
                    "tree": "G:\\example\\to\\mcp/\n    ├── mcp-clients.md\n    ├── mcp-introduction.md\n    ├── README.md\n    ├── servers/\n    │   ├── git-mcp-server.md\n    │   ├── jetbrains-mcp-server/\n    │   │   └── tools-2025.2.md\n    │   └── jetbrains-mcp-server.md\n    └── spec/\n        └── 2025-03-26/\n            ├── architecture.md\n            ├── basic/\n            │   ├── authorization.md\n            │   ├── lifecycle.md\n            │   ├── README.md\n            │   ├── transports.md\n            │   └── utilities/\n            ├── client/\n            │   ├── README.md\n            │   ├── roots.md\n            │   └── sampling.md\n            ├── README.md\n            └── server/\n                ├── prompts.md\n                ├── README.md\n                ├── resources.md\n                ├── tools.md\n                └── utilities/\n",
                    "errors": []
                  }
                }
              ],
              "isError": false
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        if 'directoryPath' not in arguments:
            log.error("Missing required argument: directoryPath")
            raise ToolError(message="Missing required argument: directoryPath", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            directory_path = arguments.get('directoryPath', None)
            if directory_path and isinstance(directory_path, str) and directory_path.strip():
                arguments['directoryPath'] = convert_path(path=directory_path, from_type=client_path_type,
                                                          to_type=server_path_type)

        try:
            if debug:
                log.debug(f"Calling list_directory_tree with arguments: {arguments}. Need convert: {path_mismatch}")
            response = await self._do_call_tool(deadline=deadline, name="list_directory_tree", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling list_directory_tree: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling list_directory_tree: {e}", code=500)

        if debug:
            log.debug(f"Original list_directory_tree response: {response.model_dump_json(indent=2)}.")

        if not path_mismatch or response.isError or not response.content:
            return response

        try:
            for c in response.content:
                if isinstance(c, TextContent):
                    import json
                    text_dict = json.loads(c.text)

                    traversed_dir = text_dict.get('traversedDirectory')
                    if traversed_dir and isinstance(traversed_dir, str) and traversed_dir.strip():
                        text_dict['traversedDirectory'] = convert_path(path=traversed_dir,
                                                                       from_type=server_path_type,
                                                                       to_type=client_path_type)

                    tree = text_dict.get('tree')
                    if tree and isinstance(tree, str) and tree.strip():
                        lines = tree.split('\n', 1)
                        if lines:
                            root_path_line = lines[0]
                            converted_root = convert_path(path=root_path_line, from_type=server_path_type,
                                                          to_type=client_path_type)
                            if len(lines) > 1:
                                text_dict['tree'] = f"{converted_root}\n{lines[1]}"
                            else:
                                text_dict['tree'] = converted_root

                    c.text = json.dumps(text_dict)
        except BaseException as e:
            import traceback
            log.warning(f"Exception converting paths in list_directory_tree response: {e}. "
                        f"Response content: {response.content}. Ignoring conversion:\n{traceback.format_exc()}")

        if debug:
            log.debug(f"Converted list_directory_tree response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_reformat_file(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "reformat_file",
              "description": "Reformats a specified file in the JetBrains IDE.\nUse this tool to apply code formatting rules to a file identified by its path.",
              "inputSchema": {
                "properties": {
                  "path": {
                    "type": "string",
                    "description": "Path relative to the project root"
                  }
                },
                "required": [
                  "path"
                ],
                "type": "object"
              }
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        if 'path' not in arguments:
            log.error("Missing required argument: path")
            raise ToolError(message="Missing required argument: path", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            path = arguments.get('path')
            if path and isinstance(path, str) and path.strip():
                arguments['path'] = convert_path(path=path, from_type=client_path_type, to_type=server_path_type)

        try:
            if debug:
                log.debug(f"Calling reformat_file with arguments: {arguments}. Need convert: {path_mismatch}")
            response = await self._do_call_tool(deadline=deadline, name="reformat_file", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling reformat_file: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling reformat_file: {e}", code=500)

        if debug:
            log.debug(f"Original reformat_file response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_rename_refactoring(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "rename_refactoring",
              "description": "        Renames a symbol (variable, function, class, etc.) in the specified file.\n        Use this tool to perform rename refactoring operations. \n        \n        The `rename_refactoring` tool is a powerful, context-aware utility. Unlike a simple text search-and-replace, \n        it understands the code's structure and will intelligently update ALL references to the specified symbol throughout the project,\n        ensuring code integrity and preventing broken references. It is ALWAYS the preferred method for renaming programmatic symbols.\n\n        Requires three parameters:\n            - pathInProject: The relative path to the file from the project's root directory (e.g., `src/api/controllers/userController.js`)\n            - symbolName: The exact, case-sensitive name of the existing symbol to be renamed (e.g., `getUserData`)\n            - newName: The new, case-sensitive name for the symbol (e.g., `fetchUserData`).\n            \n        Returns a success message if the rename operation was successful.\n        Returns an error message if the file or symbol cannot be found or the rename operation failed.",
              "inputSchema": {
                "properties": {
                  "pathInProject": {
                    "type": "string",
                    "description": "Path relative to the project root"
                  },
                  "symbolName": {
                    "type": "string",
                    "description": "Name of the symbol to rename"
                  },
                  "newName": {
                    "type": "string",
                    "description": "New name for the symbol"
                  }
                },
                "required": [
                  "pathInProject",
                  "symbolName",
                  "newName"
                ],
                "type": "object"
              }
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        required_args = ["pathInProject", "symbolName", "newName"]
        for arg in required_args:
            if arg not in arguments:
                log.error(f"Missing required argument: {arg}")
                raise ToolError(message=f"Missing required argument: {arg}", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            path = arguments.get('pathInProject', None)
            if path and isinstance(path, str) and path.strip():
                arguments['pathInProject'] = convert_path(path=path, from_type=client_path_type,
                                                          to_type=server_path_type)

        try:
            if debug:
                log.debug(f"Calling rename_refactoring with arguments: {arguments}. Need convert: {path_mismatch}")
            response = await self._do_call_tool(deadline=deadline, name="rename_refactoring", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling rename_refactoring: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling rename_refactoring: {e}", code=500)

        if debug:
            log.debug(f"Original rename_refactoring response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_replace_text_in_file(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "replace_text_in_file",
              "description": "        Replaces text in a file with flexible options for find and replace operations.\n        Use this tool to make targeted changes without replacing the entire file content.\n        This is the most efficient tool for file modifications when you know the exact text to replace.\n        \n        Requires three parameters:\n        - pathInProject: The path to the target file, relative to project root\n        - oldTextOrPatte: The text to be replaced (exact match by default)\n        - newText: The replacement text\n        \n        Optional parameters:\n        - replaceAll: Whether to replace all occurrences (default: true)\n        - caseSensitive: Whether the search is case-sensitive (default: true)\n        - regex: Whether to treat oldText as a regular expression (default: false)\n        \n        Returns one of these responses:\n        - \"ok\" when replacement happened\n        - error \"project dir not found\" if project directory cannot be determined\n        - error \"file not found\" if the file doesn't exist\n        - error \"could not get document\" if the file content cannot be accessed\n        - error \"no occurrences found\" if the old text was not found in the file\n        \n        Note: Automatically saves the file after modification",
              "inputSchema": {
                "properties": {
                  "pathInProject": {
                    "type": "string",
                    "description": "Path to target file relative to project root"
                  },
                  "oldText": {
                    "type": "string",
                    "description": "Text to be replaced"
                  },
                  "newText": {
                    "type": "string",
                    "description": "Replacement text"
                  },
                  "replaceAll": {
                    "type": "boolean",
                    "description": "Replace all occurrences"
                  },
                  "caseSensitive": {
                    "type": "boolean",
                    "description": "Case-sensitive search"
                  }
                },
                "required": [
                  "pathInProject",
                  "oldText",
                  "newText"
                ],
                "type": "object"
              }
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        required_args = ["pathInProject", "oldText", "newText"]
        for arg in required_args:
            if arg not in arguments:
                log.error(f"Missing required argument: {arg}")
                raise ToolError(message=f"Missing required argument: {arg}", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            path = arguments.get('pathInProject', None)
            if path and isinstance(path, str) and path.strip():
                arguments['pathInProject'] = convert_path(path=path, from_type=client_path_type,
                                                          to_type=server_path_type)

        try:
            if debug:
                log.debug(f"Calling replace_text_in_file with arguments: {arguments}. Need convert: {path_mismatch}")
            response = await self._do_call_tool(deadline=deadline, name="replace_text_in_file", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling replace_text_in_file: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling replace_text_in_file: {e}", code=500)

        if debug:
            log.debug(f"Original replace_text_in_file response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_search_in_files_by_regex(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "search_in_files_by_regex",
              "description": "Searches with a regex pattern within all files in the project using IntelliJ's search engine.\nPrefer this tool over reading files with command-line tools because it's much faster.\n\nThe result occurrences are surrounded with || characters, e.g. `some text ||substring|| text`",
              "inputSchema": {
                "properties": {
                  "regexPattern": {
                    "type": "string",
                    "description": "Regex patter to search for"
                  },
                  "directoryToSearch": {
                    "type": "string",
                    "description": "Directory to search in, relative to project root. If not specified, searches in the entire project."
                  },
                  "fileMask": {
                    "type": "string",
                    "description": "File mask to search for. If not specified, searches for all files. Example: `*.java`"
                  },
                  "caseSensitive": {
                    "type": "boolean",
                    "description": "Whether to search for the text in a case-sensitive manner"
                  },
                  "maxUsageCount": {
                    "type": "integer",
                    "description": "Maximum number of entries to return."
                  },
                  "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds"
                  }
                },
                "required": [
                  "regexPattern"
                ],
                "type": "object"
              }
            }

            Response example:
            {
              "content": [
                {
                  "type": "text",
                  "text": {
                    "entries": [
                      {
                        "filePath": "src\\jetbrains_proxy_mcp_server\\service\\JetbrainsMCPServerProxy.py",
                        "lineNumber": 52,
                        "lineText": "    ||tool_handlers: dict[str, Callable[[float, dict[str, Any]], Coroutine[Any, Any, CallToolResult]]]||"
                      }
                    ]
                  }
                }
              ]
            }
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        if 'regexPattern' not in arguments:
            log.error("Missing required argument: regexPattern")
            raise ToolError(message="Missing required argument: regexPattern", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            directory_to_search = arguments.get('directoryToSearch')
            if directory_to_search and isinstance(directory_to_search, str) and directory_to_search.strip():
                arguments['directoryToSearch'] = convert_path(path=directory_to_search, from_type=client_path_type,
                                                              to_type=server_path_type)

        try:
            if debug:
                log.debug(
                    f"Calling search_in_files_by_regex with arguments: {arguments}. Need convert: {path_mismatch}")
            response = await self._do_call_tool(deadline=deadline, name="search_in_files_by_regex", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling search_in_files_by_regex: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling search_in_files_by_regex: {e}", code=500)

        if debug:
            log.debug(f"Original search_in_files_by_regex response: {response.model_dump_json(indent=2)}.")

        if not path_mismatch or response.isError or not response.content:
            return response

        try:
            for c in response.content:
                if isinstance(c, TextContent):
                    import json
                    text_dict = json.loads(c.text)
                    entries = text_dict.get('entries', [])
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, dict) and 'filePath' in entry:
                                fp = entry['filePath']
                                if fp and isinstance(fp, str) and fp.strip():
                                    entry['filePath'] = convert_path(path=fp, from_type=server_path_type,
                                                                     to_type=client_path_type)
                    c.text = json.dumps(text_dict)
        except BaseException as e:
            import traceback
            log.warning(f"Exception converting filePath in search_in_files_by_regex response: {e}. "
                        f"Response content: {response.content}. Ignoring conversion:\n{traceback.format_exc()}")

        if debug:
            log.debug(f"Converted search_in_files_by_regex response: {response.model_dump_json(indent=2)}.")

        return response

    async def _do_search_in_files_by_text(self, deadline: float, arguments: dict[str, Any]) -> CallToolResult:
        """Schema:
            {
              "name": "search_in_files_by_text",
              "description": "Searches for a text substring within all files in the project using IntelliJ's search engine.\nPrefer this tool over reading files with command-line tools because it's much faster.\n\nThe result occurrences are surrounded with `||` characters, e.g. `some text ||substring|| text`",
              "inputSchema": {
                "properties": {
                  "searchText": {
                    "type": "string",
                    "description": "Text substring to search for"
                  },
                  "directoryToSearch": {
                    "type": "string",
                    "description": "Directory to search in, relative to project root. If not specified, searches in the entire project."
                  },
                  "fileMask": {
                    "type": "string",
                    "description": "File mask to search for. If not specified, searches for all files. Example: `*.java`"
                  },
                  "caseSensitive": {
                    "type": "boolean",
                    "description": "Whether to search for the text in a case-sensitive manner"
                  },
                  "maxUsageCount": {
                    "type": "integer",
                    "description": "Maximum number of entries to return."
                  },
                  "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds"
                  }
                },
                "required": [
                  "searchText"
                ],
                "type": "object"
              }
            }

            Response example: see search_in_files_by_regex
        """

        log = get_logger()
        debug = self.properties.debug_enabled

        if arguments is None:
            arguments = {}

        if 'searchText' not in arguments:
            log.error("Missing required argument: searchText")
            raise ToolError(message="Missing required argument: searchText", code=400)

        server_path_type = self.properties.server_path_type
        client_path_type = self.properties.client_path_type
        path_mismatch = server_path_type != client_path_type

        if path_mismatch:
            directory_to_search = arguments.get('directoryToSearch', None)
            if directory_to_search and isinstance(directory_to_search, str) and directory_to_search.strip():
                arguments['directoryToSearch'] = convert_path(path=directory_to_search, from_type=client_path_type,
                                                              to_type=server_path_type)

        try:
            if debug:
                log.debug(
                    f"Calling search_in_files_by_text with arguments: {arguments}. Need convert: {path_mismatch}")
            response = await self._do_call_tool(deadline=deadline, name="search_in_files_by_text", arguments=arguments)
        except ToolError:
            raise
        except BaseException as e:
            import traceback
            log.error(f"Exception calling search_in_files_by_text: {e}:\n{traceback.format_exc()}")
            raise ToolError(message=f"Exception calling search_in_files_by_text: {e}", code=500)

        if debug:
            log.debug(f"Original search_in_files_by_text response: {response.model_dump_json(indent=2)}.")

        if not path_mismatch or response.isError or not response.content:
            return response

        try:
            for c in response.content:
                if isinstance(c, TextContent):
                    import json
                    text_dict = json.loads(c.text)
                    entries = text_dict.get('entries', [])
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, dict) and 'filePath' in entry:
                                fp = entry['filePath']
                                if fp and isinstance(fp, str) and fp.strip():
                                    entry['filePath'] = convert_path(path=fp, from_type=server_path_type,
                                                                     to_type=client_path_type)
                    c.text = json.dumps(text_dict)
        except BaseException as e:
            import traceback
            log.warning(f"Exception converting filePath in search_in_files_by_text response: {e}. "
                        f"Response content: {response.content}. Ignoring conversion:\n{traceback.format_exc()}")

        if debug:
            log.debug(f"Converted search_in_files_by_text response: {response.model_dump_json(indent=2)}.")

        return response
