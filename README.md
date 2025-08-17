# JetBrains Proxy MCP Server
**Project Overview:**

- A Python-based proxy server for the JetBrains MCP (Model Context Protocol) server that acts as an intermediary between an MCP client and a JetBrains MCP server.
- The core logic resides in [`src/jetbrains_proxy_mcp_server/server.py`][server.py],
  which handles the proxy server setup and transport layer.
  The [`src/jetbrains_proxy_mcp_server/service/JetbrainsMCPServerProxy.py`][JetbrainsMCPServerProxy]
  class manages the connection to the downstream JetBrains MCP server and proxies the tool calls.
  It also includes logic to handle path conversions between different path formats (WSL, Git Bash, Windows).

Configuration is managed through the [`src/jetbrains_proxy_mcp_server/properties/MCPServerProperties.py`][MCPServerProperties.py] class,
which loads settings from a `config.yaml` file.

**Features:**

- **Proxy Functionality**: Forwards requests from MCP clients to the [JetBrains MCP server][26071-mcp-server]
- **Dual Transport Support**: Works with both Server-Sent Events (SSE) and standard I/O (stdio)
- **Path Conversion**: Handles file path conversions between different path formats (WSL, Git Bash, Windows)
- **Resilience**: Built-in retry, timeout, and restart mechanisms for robust operation
- **Tool Filtering**: Supports a curated list of JetBrains tools for controlled access



## Installation
See [pytools.sh](pytools.sh)

```
Usage: pytools.sh <command> [args...]

Commands:
  test [pytest-args...]             Always run pytest in project .venv (auto-create). If pytest missing, auto-install.
  purge                             Remove temp/build files (.venv, build, dist, caches, *.egg-info, _version.py)
  reinstall-system [pip-args...]    Reinstall into SYSTEM Python. Pass extra args to 'pip install'. No purge.
                                    Examples:
                                      pytools.sh reinstall-system --break-system-packages
                                      pytools.sh reinstall-system --no-build-isolation ".[dev]"
  reinstall-venv [pip-args...]      Reinstall into project .venv (auto-create). Pass extra args to 'pip install'. No purge.
                                    Examples:
                                      pytools.sh reinstall-venv
                                      pytools.sh reinstall-venv --no-build-isolation ".[dev]"
  upload <repository> [extra-pip-args...]  Build (sdist+wheel) and upload via twine to the named repository (e.g. pypi, testpypi).
                                    Pass extra args to 'pip install' after the default list.
                                    Examples:
                                      pytools.sh upload pypi
                                      pytools.sh upload testpypi 'build==1.2.2' 'twine==5.0.0'

Env vars:
  PYTHON_BIN   Python command to use (default: python3)
  VENV_DIR     Virtualenv path (default: $script_dir/.venv)
```

```bash
# Install the package using the provided script:
./pytools.sh reinstall-venv

./pytools.sh reinstall-system --break-system-packages

# Or install the package using pip:
pip install .
```



## Configuration
See also:

- [MCPServerProperties.py]
- [JetbrainsMCPServer.py]

Create a `config.yaml` file to configure the proxy server. The server will look for this file in the following order:

1. Path specified by the `--config` command line argument
2. `config.yaml` in the current directory
3. `~/.config/jetbrains-proxy-mcp-server/config.yaml`


### Example Configuration
```yaml
# Server configuration
server-name: "JetBrains Proxy MCP Server"
transport: "sse"  # or "stdio"
timeout: 60.0

sse-port: 41110
sse-debug-enabled: true

# JetBrains MCP server configuration
jetbrains-mcp-server:
  name: "jetbrains-mcp-server"
  url: "http://127.0.0.1:64342/sse"
  timeout: 35.0
  sse-read-timeout: 300.0
  start-timeout: 120.0
  stop-timeout: 30.0
  max-attempts: 5
  initial-backoff: 1.0
  max-backoff: 60.0
  backoff-multiplier: 3.0
  debug-enabled: true
  client-path-type: "wsl"  # or ""windows_git_bash" or "windows"
  server-path-type: "windows"  # or "wsl" or "windows_git_bash"
```


### [Proxy Server Properties][MCPServerProperties.py]
| Property            | Default                    | Description                       |
|---------------------|----------------------------|-----------------------------------|
| `server-name`       | JetBrains Proxy MCP Server | Name of the proxy server          |
| `transport`         | sse                        | Transport type: "sse" or "stdio"  |
| `sse-port`          | 41110                      | Port for SSE server               |
| `sse-debug-enabled` | true                       | Enable SSE debug mode             |
| `timeout`           | 60.0                       | Timeout for tool calls in seconds |


### [JetBrains MCP Server Properties][JetbrainsMCPServer.py]
| Property             | Default                    | Description                              |
|----------------------|----------------------------|------------------------------------------|
| `name`               | jetbrains-mcp-server       | Name of the JetBrains MCP server         |
| `url`                | http://127.0.0.1:64342/sse | URL of the JetBrains MCP server          |
| `headers`            | {}                         | Additional headers for requests          |
| `timeout`            | 35.0                       | Timeout for requests to JetBrains server |
| `sse-read-timeout`   | 300.0                      | SSE read timeout                         |
| `start-timeout`      | 120.0                      | Timeout for server startup               |
| `stop-timeout`       | 30.0                       | Timeout for server shutdown              |
| `max-attempts`       | 5                          | Maximum retry attempts                   |
| `initial-backoff`    | 1.0                        | Initial backoff time in seconds          |
| `max-backoff`        | 60.0                       | Maximum backoff time in seconds          |
| `backoff-multiplier` | 3.0                        | Backoff multiplier for retries           |
| `client-path-type`   | wsl                        | Path type for the client                 |
| `server-path-type`   | windows                    | Path type for the JetBrains server       |
| `debug-enabled`      | true                       | Enable debug logging                     |


### Environment Variables
See also:

- [MCPServerProperties.py]
- [logger.py]

Configuration can also be set using environment variables:

- `JETBRAINS_PROXY_MCP_SERVER_CONFIG` - Path to config file
- `JETBRAINS_PROXY_MCP_SERVER_NAME` - Server name
- `JETBRAINS_PROXY_MCP_SERVER_TRANSPORT` - Transport type
- `JETBRAINS_PROXY_MCP_SERVER_TIMEOUT` - Tool timeout

For stdio transport, you must set:

```bash
export SIMP_LOGGER_LOG_CONSOLE_ENABLED=False
```



## MCP Configuration
### JSON
**sse, wsl:**

```json
{
  "mcpServers": {
    "jetbrains": {
      "url": "http://127.0.0.1:41110/sse"
    }
  }
}
```

**sse, windows:**

```json
{
  "mcpServers": {
    "jetbrains": {
      "url": "http://127.0.0.1:41111/sse"
    }
  }
}
```

**stdio, windows:**

```bash
pip install jetbrains-proxy-mcp-server --upgrade --force-reinstall --extra-index-url http://127.0.0.1:8081/repository/pypi-group/simple --trusted-host 127.0.0.1
```

```json
{
  "mcpServers": {
    "jetbrains": {
      "command": "jetbrains-proxy-mcp-server",
      "args": [
        "--config",
        "c:/Users/<USER>/.config/jetbrains-proxy-mcp-server/config.yaml"
      ],
      "env": {
        "SIMP_LOGGER_LOG_CONSOLE_ENABLED": "False",
        "SIMP_LOGGER_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```



## Running the Server
Start the server with:

```bash
jetbrains-proxy-mcp-server

# Or:
jetbrains-proxy-mcp-server --config /path/to/your/config.yaml
```

If no config path is provided, the server will search for a `config.yaml` file in the default locations.



## Supported Tools
The proxy supports a curated list of JetBrains tools:

**MCP Server v252.xxx**

- `get_all_open_file_paths` - Get paths of all open files
- `get_file_problems` - Analyze file for errors and warnings
- `get_file_text_by_path` - Retrieve text content of a file
- `get_project_dependencies` - Get project dependencies
- `get_project_modules` - Get project modules
- `get_project_problems` - Get project-wide problems
- `list_directory_tree` - List directory contents in tree format
- `reformat_file` - Reformat a file
- `rename_refactoring` - Rename a symbol across the project
- `replace_text_in_file` - Replace text in a file
- `search_in_files_by_regex` - Search files using regex
- `search_in_files_by_text` - Search files for text



## Path Conversion
The proxy handles path conversions between different operating systems:

- **WSL**: `/mnt/c/path/to/file`
- **Git Bash**: `/c/path/to/file`
- **Windows**: `C:\path\to\file`

Configure `client-path-type` and `server-path-type` in your config to match your environments.



## Development
### Development Conventions
* The project uses `setuptools` for packaging.
* Dependencies are managed in `pyproject.toml`.
* The code follows standard Python conventions.
* Logging is implemented using the `logging` module.
* The project uses `anyio` for asynchronous operations.
* The server uses `uvicorn` when running with the SSE transport.


### Installing dependencies
To install the necessary dependencies, run:

```bash
uv sync --no-install-project --extra test
```


### Testing
Run tests with pytest:

```bash
./pytools test tests/test_xxx.py

# Or use the command directly:
pytest tests/test_xxx.py

# Or test all:
pytest
```


### Dependencies
- Python >= 3.10
- mcp >= 1.4.0
- pydantic >= 2.0
- typing >= 3.7.4.3
- pyyaml >= 6.0.2
- anyio >= 4.3.0


## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.


[server.py]: src/jetbrains_proxy_mcp_server/server.py
[JetbrainsMCPServerProxy]: src/jetbrains_proxy_mcp_server/service/JetbrainsMCPServerProxy.py
[MCPServerProperties.py]: src/jetbrains_proxy_mcp_server/properties/MCPServerProperties.py
[JetbrainsMCPServer.py]: src/jetbrains_proxy_mcp_server/properties/JetbrainsMCPServer.py
[logger.py]: src/jetbrains_proxy_mcp_server/logger.py
[26071-mcp-server]: https://plugins.jetbrains.com/plugin/26071-mcp-server
