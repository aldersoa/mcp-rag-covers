# server.py
# pip install mcp httpx
from mcp.server.fastmcp import FastMCP
from typing import List, Dict, Any
from covers_core import search_cover_art_core

mcp = FastMCP("covers-py")

@mcp.tool()
async def search_cover_art(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Return album covers for a free-form query (e.g., 'show me covers from metal bands')."""
    return await search_cover_art_core(query, limit)

if __name__ == "__main__":
    mcp.run()  # serves MCP over stdio
