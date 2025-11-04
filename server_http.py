# server_http.py
import os
import json
from typing import Any, Dict, List, Optional
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware
import uvicorn

# Reuse your existing helpers from covers_core
from covers_core import (
    route,
    search_artists_by_query,
    search_artists_by_tag,
    release_groups_for_artist,
    mb_get,  # to fetch release-group details for "fetch"
)

# ---------------- JSON-RPC helpers ----------------

def rpc_ok(_id: Any, result: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": _id, "result": result})

def rpc_err(_id: Any, code: int, msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": _id, "error": {"code": code, "message": msg}},
        status_code=status
    )

# ---------------- Tool Schemas (per ChatGPT docs) ----------------
# Keep schemas tight; some builders are strict.
SEARCH_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "SearchArgs",
    "type": "object",
    "properties": {
        "query": {"type": "string", "title": "Query"}
    },
    "required": ["query"],
    "additionalProperties": False
}

FETCH_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "FetchArgs",
    "type": "object",
    "properties": {
        "id": {"type": "string", "title": "ID"}
    },
    "required": ["id"],
    "additionalProperties": False
}

TOOLS = [
    {
        "name": "search",
        "description": "Search music release groups by query; returns [{id,title,url}].",
        # Provide both camelCase and snake_case for compatibility
        "inputSchema": SEARCH_SCHEMA,
        "input_schema": SEARCH_SCHEMA,
    },
    {
        "name": "fetch",
        "description": "Fetch full details for a release-group by ID; returns {id,title,text,url,metadata}.",
        "inputSchema": FETCH_SCHEMA,
        "input_schema": FETCH_SCHEMA,
    },
]

MB_BASE = "https://musicbrainz.org"
def mb_rg_url(rgid: str) -> str:
    return f"{MB_BASE}/release-group/{rgid}"

# ---------------- Minimal health/OPTIONS ----------------

async def health_mcp(_request):
    return JSONResponse({"ok": True, "mcp": True, "path": "/mcp"})

async def options_mcp(_request):
    # 204 is fine; CORS middleware adds allow-* headers.
    return PlainTextResponse("", status_code=204)

# ---------------- Core: implement search + fetch exactly as ChatGPT expects ----

async def tool_search(query: str, limit: int = 12) -> Dict[str, Any]:
    """
    Build results for ChatGPT 'search' tool:
      returns {"results": [{"id": rgid, "title": "...", "url": "..."}]}
    """
    routed = route(query)
    # Choose ONE artist similar to covers_core logic (top-1)
    artists: List[Dict[str, Any]] = []
    raw = await search_artists_by_query(query, limit=3)
    artists = raw[:1]
    if not artists and routed["type"] == "artist" and routed["value"] != query:
        ra = await search_artists_by_query(routed["value"], limit=3)
        artists = ra[:1]
    if not artists and routed["type"] == "tag":
        ta = await search_artists_by_tag(routed["value"], limit=5)
        artists = ta[:1]

    if not artists:
        return {"results": []}

    a = artists[0]
    aid, aname = a["id"], a["name"]
    rgs = await release_groups_for_artist(aid, limit=min(limit, 24))
    results = []
    for rg in rgs[:limit]:
        rgid = rg["id"]
        title = rg.get("title", "Untitled")
        # Compose a human-friendly title for list UI
        pretty_title = f"{aname} — {title}"
        results.append({
            "id": rgid,
            "title": pretty_title,
            "url": mb_rg_url(rgid),  # canonical URL for citation
        })
    return {"results": results}

async def tool_fetch(rgid: str) -> Dict[str, Any]:
    """
    Build a single document object for ChatGPT 'fetch' tool:
      returns {id,title,text,url,metadata}
    We'll query MusicBrainz for release-group details and produce a readable 'text'.
    """
    # Get release-group JSON from MB
    rg = await mb_get("release-group", {"id": rgid})
    if not rg:
        # Some MB deployments require /release-group/<id> without fmt; above helper uses ws/2
        # Try a direct fallback:
        rg = await mb_get("release-group/" + rgid, {})
    if not rg:
        # Minimal fallback
        doc = {
            "id": rgid,
            "title": "Unknown release-group",
            "text": f"No details found for release-group {rgid}.",
            "url": mb_rg_url(rgid),
            "metadata": {},
        }
        return doc

    # Title & artist
    title = rg.get("title", "Untitled")
    artist_credit = rg.get("artist-credit") or rg.get("artistCredit") or []
    artist_name = None
    if artist_credit and isinstance(artist_credit, list):
        first = artist_credit[0]
        # MB can return dicts with nested "artist": {"name": ...}
        if isinstance(first, dict):
            artist_name = (first.get("artist") or {}).get("name") or first.get("name")
    pretty_title = f"{artist_name} — {title}" if artist_name else title

    # Build a readable text body (you can expand this later)
    first_date = rg.get("first-release-date") or rg.get("firstReleaseDate")
    primary_type = rg.get("primary-type") or rg.get("primaryType")
    secondary_types = rg.get("secondary-types") or rg.get("secondaryTypes") or []

    lines = []
    lines.append(f"Title: {title}")
    if artist_name:
        lines.append(f"Artist: {artist_name}")
    if first_date:
        lines.append(f"First release: {first_date}")
    if primary_type:
        lines.append(f"Primary type: {primary_type}")
    if secondary_types:
        lines.append(f"Secondary types: {', '.join(secondary_types)}")
    lines.append(f"MusicBrainz URL: {mb_rg_url(rgid)}")

    doc = {
        "id": rgid,
        "title": pretty_title,
        "text": "\n".join(lines),
        "url": mb_rg_url(rgid),
        "metadata": {
            "mb_release_group_id": rgid,
        },
    }
    return doc

# ---------------- JSON-RPC endpoint ----------------

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

    # Optional initialize for compatibility
    if method == "initialize":
        return rpc_ok(_id, {
            "serverInfo": {"name": "covers-mcp", "version": "0.2.0"},
            "protocol": "mcp",
            "capabilities": {"tools": {"listChanged": False}}
        })

    if method == "tools/list":
        return rpc_ok(_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {}) or {}

        if name == "search":
            q = args.get("query")
            if not isinstance(q, str) or not q.strip():
                return rpc_err(_id, -32602, "Missing required argument: query")
            # ChatGPT expects: content → one item → type=text, text="<JSON string>"
            payload = await tool_search(q)
            return rpc_ok(_id, {
                "content": [
                    {"type": "text", "text": json.dumps(payload)}
                ]
            })

        if name == "fetch":
            rid = args.get("id")
            if not isinstance(rid, str) or not rid.strip():
                return rpc_err(_id, -32602, "Missing required argument: id")
            payload = await tool_fetch(rid)
            return rpc_ok(_id, {
                "content": [
                    {"type": "text", "text": json.dumps(payload)}
                ]
            })

        return rpc_err(_id, -32601, f"Unknown tool: {name}")

    return rpc_err(_id, -32601, "Method not found")

# ---------------- ASGI app & CORS ----------------

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
