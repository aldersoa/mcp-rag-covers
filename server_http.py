# server_http.py
import os
from typing import Any, Dict, List
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
import uvicorn

from covers_core import search_cover_art_core

# ---- JSON-RPC helpers --------------------------------------------------------

def rpc_result(_id: Any, result: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": _id, "result": result})

def rpc_error(_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": _id, "error": {"code": code, "message": message}}, status_code=400)

# ---- MCP-compatible schema ----------------------------------------------------

TOOL = {
    "name": "search_cover_art",
    "description": "Return album covers for a free-form query (e.g., 'show me covers from metal bands' or 'by metallica').",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "number"}
        },
        "required": ["query"]
    }
}

async def mcp_endpoint(request):
    if request.method != "POST":
        return PlainTextResponse("MCP endpoint expects POST JSON-RPC 2.0", status_code=405)
    try:
        body = await request.json()
    except Exception:
        return PlainTextResponse("Bad Request", status_code=400)

    _id = body.get("id")
    method = body.get("method")
    params = body.get("params", {}) or {}

    # tools/list
    if method == "tools/list":
        return rpc_result(_id, {"tools": [TOOL]})

    # tools/call
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        if name != TOOL["name"]:
            return rpc_error(_id, -32601, f"Unknown tool: {name}")
        query = args.get("query")
        limit = int(args.get("limit", 8))
        if not isinstance(query, str) or not query.strip():
            return rpc_error(_id, -32602, "Missing required argument: query")

        # call your core function
        data = await search_cover_art_core(query, limit, debug=False)
        results: List[Dict[str, Any]] = data["results"]

        # Return MCP-style content
        return rpc_result(_id, {"content": [{"type": "json", "json": results}]})

    # method not found
    return rpc_error(_id, -32601, "Method not found")

app = Starlette(debug=False, routes=[Route("/", mcp_endpoint, methods=["POST"])])

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
