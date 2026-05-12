def create_mcp_server():
    # Lazy import to avoid loading MCP tool modules at app import time.
    from .server import create_mcp_server as _create_mcp_server

    return _create_mcp_server()


__all__ = ["create_mcp_server"]
