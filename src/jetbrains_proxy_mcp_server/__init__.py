from .server import serve


def main():
    import os
    import argparse

    if os.getenv("SIMP_LOGGER_LOG_FILE") is None:
        os.environ["SIMP_LOGGER_LOG_FILE"] = os.path.join(
            os.path.expanduser("~"), "logs", "jetbrains-proxy-mcp-server", "mcp.log")

    parser = argparse.ArgumentParser(
        description="JetBrains Proxy MCP Server: A server for proxying JetBrains MCP server"
    )
    parser.add_argument("--config", type=str, help="Path to the config file")

    args = parser.parse_args()
    serve(args.config)


if __name__ == "__main__":
    main()
