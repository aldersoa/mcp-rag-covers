import os
import json
from typing import Any, Dict, List
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
import uvicorn

# ---------- local helpers ----------
from covers_core import (
    route,
    search_artists_by_query,
    search_artists_by_tag,
    release_groups_for_artist,
    mb_get,
)

def rpc_ok(_id: Any, result: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": _id, "result": result})

def rpc_err(_id: Any, code: int, msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": _id, "error": {"code": code, "message": msg}},
        status_code=status,
    )

SEARCH_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "SearchArgs",
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}
FETCH_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "FetchArgs",
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["id"],
}
TOOLS = [
    {
        "name": "search",
        "description": "Search music release groups by query",
        "inputSchema": SEARCH_SCHEMA,
        "input_schema": SEARCH_SCHEMA,
    },
    {
        "name": "fetch",
        "description": "Fetch details for a release group by ID",
        "inputSchema": FETCH_SCHEMA,
        "input_schema": FETCH_SCHEMA,
    },
]

MB_BASE = "https://musicbrainz.org"
def mb_rg_url(rgid: str) -> str:
    return f"{MB_BASE}/release-group/{rgid}"

async def health_mcp(_):
    return JSONResponse({"ok": True, "mcp": True})

async def options_mcp(_):
    return PlainTextResponse("", status_code=204)

async def tool_search(query: str, limit: int = 12) -> Dict[str, Any]:
    routed = route(query)
    artists = await search_artists_by_query(query, limit=3)
    if not artists and routed["type"] == "tag":
        artists = await search_artists_by_tag(routed["value"], limit=5)
    if not artists:
        return {"results": []}
    a = artists[0]
    aid, aname = a["id"], a["name"]
    rgs = await release_groups_for_artist(aid, limit=min(limit, 24))
    results = [
        {"id": rg["id"], "title": f"{aname} — {rg.get('title','Untitled')}", "url": mb_rg_url(rg["id"])}
        for rg in rgs[:limit]
    ]
    return {"results": results}

async def tool_fetch(rgid: str) -> Dict[str, Any]:
    rg = await mb_get("release-group", {"id": rgid}) or await mb_get("release-group/" + rgid, {})
    if not rg:
        return {"id": rgid, "title": "Unknown", "text": "No details found.", "url": mb_rg_url(rgid)}
    title = rg.get("title", "Untitled")
    ac = rg.get("artist-credit") or rg.get("artistCredit") or []
    artist = (ac[0].get("artist", {}).get("name") if ac and isinstance(ac[0], dict) else None)
    text = f"Title: {title}\nArtist: {artist}\nMusicBrainz URL: {mb_rg_url(rgid)}"
    return {"id": rgid, "title": f"{artist} — {title}" if artist else title, "text": text, "url": mb_rg_url(rgid)}

async def mcp_endpoint(request):
    if request.method != "POST":
        return PlainTextResponse("MCP expects POST JSON-RPC 2.0", status_code=405)
    try:
        body = await request.json()
    except Exception:
        return PlainTextResponse("Bad Request", status_code=400)
    _id, method, params = body.get("id"), body.get("method"), body.get("params", {}) or {}
    if method == "initialize":
        return rpc_ok(_id, {"serverInfo": {"name": "covers-mcp", "version": "0.2.0"},
                            "protocol": "mcp", "capabilities": {"tools": {"listChanged": False}}})
    if method == "tools/list":
        return rpc_ok(_id, {"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {}) or {}
        if name == "search":
            payload = await tool_search(args.get("query", ""))
            return rpc_ok(_id, {"content": [{"type": "text", "text": json.dumps(payload)}]})
        if name == "fetch":
            payload = await tool_fetch(args.get("id", ""))
            return rpc_ok(_id, {"content": [{"type": "text", "text": json.dumps(payload)}]})
        return rpc_err(_id, -32601, f"Unknown tool: {name}")
    return rpc_err(_id, -32601, "Method not found")

# ---------- app ----------
app = Starlette(
    debug=False,
    routes=[
        Route("/mcp", mcp_endpoint, methods=["POST"]),
        Route("/mcp", health_mcp, methods=["GET", "HEAD"]),
        Route("/mcp", options_mcp, methods=["OPTIONS"]),
    ],
)

# static files
public_dir = os.path.join(os.path.dirname(__file__), "public")
if os.path.isdir(public_dir):
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)