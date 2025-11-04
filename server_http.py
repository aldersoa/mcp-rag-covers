# server_http.py
import os
from typing import List, Dict, Any
from mcp.server.fastmcp import FastMCP  # same SDK you already used
from covers_core import search_cover_art_core

mcp = FastMCP("covers-mcp")

@mcp.tool()
async def search_cover_art(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Return album covers for a free-form query (e.g., "show me covers from metallica").
    """
    data = await search_cover_art_core(query, limit, debug=False)
    return data["results"]  # just the list for MCP callers

if __name__ == "__main__":
    # Render provides PORT; bind 0.0.0.0 so it’s reachable
    port = int(os.getenv("PORT", "8000"))
    # Streamable HTTP transport (a remote MCP endpoint) mounted at /mcp
    # Clients (like ChatGPT) will connect to https://<your-service>.onrender.com/mcp
    mcp.run(transport="http", host="0.0.0.0", port=port, path="/mcp")
