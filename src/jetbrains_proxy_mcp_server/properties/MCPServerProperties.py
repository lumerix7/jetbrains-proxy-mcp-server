"""MCPServerProperties.py: This file contains the properties of the Jetbrains Proxy MCP Server."""

from mcp import ErrorData, McpError
from yaml import YAMLError

from .JetbrainsMCPServer import JetbrainsMCPServer
from ..logger import get_logger
from ..utils import get_str_property, get_int_property, get_float_property, get_bool_property


class MCPServerProperties:
    server_name: str = "Jetbrains Proxy MCP Server"

    # Transport type for MCP communication, defaults to sse, available options are 'stdio', 'sse'.
    transport: str = "sse"
    sse_transport_endpoint: str = "/messages/"
    sse_bind_host: str = "0.0.0.0"
    sse_port: int = 41110
    sse_debug_enabled: bool = True

    # Total timeout time of one MCP calling, in seconds, defaults to 60.0 seconds.
    timeout: float = 60.0

    jetbrains_mcp_server: JetbrainsMCPServer = JetbrainsMCPServer()

    def __init__(self):
        pass

    def load(self, properties_path: str = None):
        import os

        log = get_logger()

        # Check if properties_path is provided
        by_env_var = False
        if properties_path is None:
            default_path = "config.yaml" if os.path.exists("config.yaml") \
                else os.path.join(os.path.expanduser("~"), ".config", "jetbrains-proxy-mcp-server", "config.yaml")
            properties_path = os.getenv("JETBRAINS_PROXY_MCP_SERVER_CONFIG", default_path)
            if not properties_path:
                log.error("Properties path not found in environment variable JETBRAINS_PROXY_MCP_SERVER_CONFIG.")
                raise McpError(ErrorData(
                    code=404,
                    message="Properties path not found in environment variable JETBRAINS_PROXY_MCP_SERVER_CONFIG"))
            by_env_var = True
        # Check exists
        if not os.path.exists(properties_path):
            if by_env_var:
                log.error(f"Properties file {properties_path} does not exist, please set the environment variable "
                          f"JETBRAINS_PROXY_MCP_SERVER_CONFIG to the path of the properties file.")
            else:
                log.error(f"Properties file {properties_path} does not exist.")
            raise McpError(ErrorData(code=404, message=f"Properties file {properties_path} does not exist"))

        log.info(f"Loading properties from {properties_path}...")

        try:
            import yaml

            with open(properties_path, 'r', encoding='utf-8') as file:
                properties = yaml.safe_load(file)

            if properties is None:
                log.warning(f"Properties file {properties_path} is empty.")
                properties = {}

            # Convert hyphen to underscore in keys
            properties_tmp = {}
            for k, v in properties.items():
                new_key = k.replace("-", "_") if isinstance(k, str) else k
                properties_tmp[new_key] = v
            properties = properties_tmp

            self._load_basic_properties(properties)
            self._load_jetbrains_mcp_server_properties(properties)

        except FileNotFoundError:
            log.error(f"Properties file not found: {properties_path}.")
            raise McpError(ErrorData(code=404, message=f"Properties file not found: {properties_path}"))
        except YAMLError as e:
            log.error(f"Error parsing YAML file: {e}.")
            raise McpError(ErrorData(code=400, message=f"Error parsing YAML file: {e}"))
        except Exception as e:
            if not isinstance(e, McpError):
                import traceback
                log.error(f"Error reading properties file: {e}.\n{traceback.format_exc()}")
                raise McpError(ErrorData(code=400, message=f"Error reading properties file: {e}"))
            raise e

    def _load_basic_properties(self, properties: dict):
        log = get_logger()

        # Name
        name = get_str_property(props=properties, prop_name='server_name',
                                env_var_name='JETBRAINS_PROXY_MCP_SERVER_NAME')
        if name:
            self.server_name = name.strip()
            log.info(f"Server name set to: {self.server_name}.")
        # Transport
        log.info(f"Loading transport properties {properties}...")
        transport = get_str_property(props=properties, prop_name='transport',
                                     env_var_name='JETBRAINS_PROXY_MCP_SERVER_TRANSPORT')
        if transport and transport in ['stdio', 'sse']:
            self.transport = transport.strip()
            log.info(f"Transport set to: {self.transport}.")

        if self.transport == 'sse':
            # SSE endpoint
            endpoint = get_str_property(props=properties, prop_name='sse_transport_endpoint',
                                        env_var_name='JETBRAINS_PROXY_MCP_SERVER_SSE_TRANSPORT_ENDPOINT')
            if endpoint:
                self.sse_transport_endpoint = endpoint.strip()
                log.info(f"SSE transport endpoint set to: {self.sse_transport_endpoint}.")
            # SSE bind host
            host = get_str_property(props=properties, prop_name='sse_bind_host',
                                    env_var_name='JETBRAINS_PROXY_MCP_SERVER_SSE_BIND_HOST')
            if host:
                self.sse_bind_host = host.strip()
                log.info(f"SSE bind host set to: {self.sse_bind_host}.")
            # SSE port
            port = get_int_property(props=properties, prop_name='sse_port',
                                    env_var_name='JETBRAINS_PROXY_MCP_SERVER_SSE_PORT')
            if port is not None and 0 < port < 65536:
                self.sse_port = port
                log.info(f"SSE port set to: {self.sse_port}.")
            # SSE debug enabled
            debug_enabled = get_bool_property(props=properties, prop_name='sse_debug_enabled',
                                              env_var_name='JETBRAINS_PROXY_MCP_SERVER_SSE_DEBUG_ENABLED')
            if debug_enabled is not None:
                self.sse_debug_enabled = debug_enabled
                log.info(f"SSE debug enabled set to: {self.sse_debug_enabled}.")

        timeout = get_float_property(props=properties, prop_name='timeout',
                                     env_var_name='JETBRAINS_PROXY_MCP_SERVER_TIMEOUT')
        if timeout is not None and timeout >= 0.1:
            self.timeout = timeout
            log.info(f"Tool timeout set to: {self.timeout}.")

    def _load_jetbrains_mcp_server_properties(self, properties: dict):
        log = get_logger()

        server_dict = properties.get('jetbrains_mcp_server', {})
        if not isinstance(server_dict, dict):
            log.warning("Jetbrains MCP server properties are not a dictionary, skipping.")
            return

        server_props = {}
        for k, v in server_dict.items():
            new_key = k.replace("-", "_") if isinstance(k, str) else k
            server_props[new_key] = v

        self.jetbrains_mcp_server = JetbrainsMCPServer(**server_props)
        log.info(f"Jetbrains MCP server properties loaded: {self.jetbrains_mcp_server.model_dump_json(indent=2)}.")
