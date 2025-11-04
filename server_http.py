# server_http.py
import os
from typing import List, Dict, Any
from mcp.server.fastmcp import FastMCP
from covers_core import search_cover_art_core

mcp = FastMCP("covers-mcp")

@mcp.tool()
async def search_cover_art(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Return album covers for a free-form query."""
    data = await search_cover_art_core(query, limit, debug=False)
    return data["results"]

if __name__ == "__main__":
    # Serve MCP over HTTP at the ROOT path "/"
    port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="http", host="0.0.0.0", port=port, path="/")
