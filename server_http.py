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
    return JSONResponse(
        {"jsonrpc": "2.0", "id": _id, "error": {"code": code, "message": msg}},
        status_code=status
    )

TOOL = {
    "name": "search_cover_art",
    "description": "Return album covers for a free-form query (e.g., 'by metallica' or 'metal bands').",
    "inputSchema": {
        # Switch to draft-07 for maximum compatibility
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "SearchCoverArtArgs",
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Query",
                "description": "Free-form prompt like 'by metallica' or 'show me covers from metal bands'."
            },
            "limit": {
                "type": "integer",
                "title": "Limit",
                "minimum": 1,
                "maximum": 50,
                "default": 8,
                "description": "Max number of results to return."
            }
        },
        "required": ["query"],
        "additionalProperties": False
    }
}

async def health_mcp(_request):
    return JSONResponse({"ok": True, "mcp": True, "path": "/mcp"})

async def options_mcp(_request):
    # IMPORTANT: 204 (not 200) for preflight
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
        lim = args.get("limit", 8)
        try:
            lim = int(lim)
        except Exception:
            lim = 8
        lim = max(1, min(50, lim))
        if not isinstance(q, str) or not q.strip():
            return rpc_err(_id, -32602, "Missing required argument: query")

        data = await search_cover_art_core(q, lim, debug=False)
        results: List[Dict[str, Any]] = data["results"][:lim]
        return rpc_ok(_id, {"content": [{"type": "json", "json": results}]})

    return rpc_err(_id, -32601, "Method not found")

app = Starlette(
    debug=False,
    routes=[
        Route("/mcp", mcp_endpoint, methods=["POST"]),
        Route("/mcp", health_mcp, methods=["GET", "HEAD"]),
        Route("/mcp", options_mcp, methods=["OPTIONS"]),
    ],
)

# Permissive CORS so connector preflights succeed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
