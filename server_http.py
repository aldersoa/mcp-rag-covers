# server_http.py
import os
from typing import List, Dict, Any
from mcp.server.fastmcp import FastMCP
from mcp.server.http import HTTPServer  # <-- uses the HTTP transport helper
from covers_core import search_cover_art_core

mcp = FastMCP("covers-mcp")

@mcp.tool()
async def search_cover_art(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Return album covers for a free-form query."""
    data = await search_cover_art_core(query, limit, debug=False)
    return data["results"]

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    # Serve MCP over HTTP at the ROOT path "/"
    HTTPServer(mcp.app).run(host="0.0.0.0", port=port, path="/")
