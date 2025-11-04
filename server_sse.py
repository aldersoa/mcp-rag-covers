# server_sse.py
import os, json
from fastmcp import FastMCP

# ---- import your existing helpers (adjust names if needed) ----
from covers_core import (
    route,
    search_artists_by_query,
    search_artists_by_tag,
    release_groups_for_artist,
    mb_get,
)

app = FastMCP(
    name="covers-mcp",
    version="0.3.0",
)

# ---- Tool: search (returns text content with JSON string) ----
@app.tool(
    name="search",
    description="Search music release groups by query; returns [{id,title,url}].",
    input_schema={
        "type": "object",
        "properties": { "query": { "type": "string" } },
        "required": ["query"],
        "additionalProperties": False,
    },
)
async def search_tool(query: str) -> str:
    # Build ChatGPT-compatible payload: {"results":[{id,title,url},...]}
    routed = route(query)
    # pick a likely artist (top-1) similar to your HTTP version
    artists = await search_artists_by_query(query, limit=3)
    if not artists and routed["type"] == "artist" and routed["value"] != query:
        artists = await search_artists_by_query(routed["value"], limit=3)
    if not artists and routed["type"] == "tag":
        artists = await search_artists_by_tag(routed["value"], limit=5)
    if not artists:
        return json.dumps({"results": []})

    a = artists[0]
    aid, aname = a["id"], a["name"]
    rgs = await release_groups_for_artist(aid, limit=12)
    results = []
    for rg in rgs[:12]:
        rgid = rg["id"]
        title = rg.get("title", "Untitled")
        pretty = f"{aname} — {title}"
        results.append({
            "id": rgid,
            "title": pretty,
            "url": f"https://musicbrainz.org/release-group/{rgid}",
        })
    return json.dumps({"results": results})

# ---- Tool: fetch (returns text content with JSON string) ----
@app.tool(
    name="fetch",
    description="Fetch full details for a release-group by ID; returns {id,title,text,url,metadata}.",
    input_schema={
        "type": "object",
        "properties": { "id": { "type": "string" } },
        "required": ["id"],
        "additionalProperties": False,
    },
)
async def fetch_tool(id: str) -> str:
    rg = await mb_get("release-group", {"id": id})
    if not rg:
        rg = await mb_get("release-group/" + id, {})
    title = (rg or {}).get("title", "Unknown release-group")

    artist_name = None
    ac = (rg or {}).get("artist-credit") or (rg or {}).get("artistCredit") or []
    if ac and isinstance(ac, list) and isinstance(ac[0], dict):
        artist_name = (ac[0].get("artist") or {}).get("name") or ac[0].get("name")

    pretty_title = f"{artist_name} — {title}" if artist_name else title
    first_date = (rg or {}).get("first-release-date") or (rg or {}).get("firstReleaseDate")
    primary_type = (rg or {}).get("primary-type") or (rg or {}).get("primaryType")
    secondary_types = (rg or {}).get("secondary-types") or (rg or {}).get("secondaryTypes") or []

    lines = [f"Title: {title}"]
    if artist_name: lines.append(f"Artist: {artist_name}")
    if first_date: lines.append(f"First release: {first_date}")
    if primary_type: lines.append(f"Primary type: {primary_type}")
    if secondary_types: lines.append(f"Secondary types: {', '.join(secondary_types)}")
    lines.append(f"MusicBrainz URL: https://musicbrainz.org/release-group/{id}")

    doc = {
        "id": id,
        "title": pretty_title,
        "text": "\n".join(lines),
        "url": f"https://musicbrainz.org/release-group/{id}",
        "metadata": { "mb_release_group_id": id },
    }
    return json.dumps(doc)

if __name__ == "__main__":
    # Start FastMCP in SSE mode at /mcp (Render will set PORT)
    port = int(os.getenv("PORT", "8000"))
    # NOTE: pass only supported args; FastMCP handles host internally
    app.run(transport="sse", path="/mcp", port=port)
