# server_http.py
import os
from typing import Any, Dict, List
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from covers_core import search_cover_art_core

def rpc_ok(_id: Any, result: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": _id, "result": result})

def rpc_err(_id: Any, code: int, msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": _id,
                         "error": {"code": code, "message": msg}}, status_code=status)

TOOL = {
    "name": "search_cover_art",
    "description": "Return album covers for a free-form query (e.g., 'by metallica' or 'metal bands').",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "number"}
        },
        "required": ["query"]
    }
}

async def health(_request):
    return JSONResponse({"ok": True, "mcp": True})

async def options_root(_request):
    # Satisfy any preflight / generic probe
    return PlainTextResponse("", status_code=204)

async def mcp_endpoint(request):
    if request.method != "POST":
        return PlainTextResponse("MCP expects POST JSON-RPC 2.0", status_code=405)

    try:
        body = await request.json()
    except Exception:
        return PlainTextResponse("Bad Request", status_code=400)

    _id = body.get("id")
    method = body.get("method")
    params = body.get("params", {}) or {}

    # Optional: minimal initialize handler (some clients probe it)
    if method == "initialize":
        return rpc_ok(_id, {
            "serverInfo": {"name": "covers-mcp", "version": "0.1.0"},
            "protocol": "mcp",
            "capabilities": {"tools": {"listChanged": False}}
        })

    if method == "tools/list":
        return rpc_ok(_id, {"tools": [TOOL]})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        if name != TOOL["name"]:
            return rpc_err(_id, -32601, f"Unknown tool: {name}")
        q = args.get("query")
        lim = int(args.get("limit", 8))
        if not isinstance(q, str) or not q.strip():
            return rpc_err(_id, -32602, "Missing required argument: query")
        data = await search_cover_art_core(q, lim, debug=False)
        results: List[Dict[str, Any]] = data["results"]
        return rpc_ok(_id, {"content": [{"type": "json", "json": results[:lim]}]})

    return rpc_err(_id, -32601, "Method not found")

app = Starlette(debug=False, routes=[
    Route("/", mcp_endpoint, methods=["POST"]),
    Route("/", health, methods=["GET"]),
    Route("/", options_root, methods=["OPTIONS"]),  # <-- explicit OPTIONS handler
])

# Permissive CORS so the connector’s preflight succeeds
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],   # allow all for simplicity
    allow_headers=["*"],   # allow Authorization, etc.
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
