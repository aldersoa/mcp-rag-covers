# server_sse.py
import os, json
from fastmcp import FastMCP

# Reuse your existing helpers from covers_core
from covers_core import (
    route,
    search_artists_by_query,
    search_artists_by_tag,
    release_groups_for_artist,
    mb_get,
)

app = FastMCP(name="covers-mcp", version="0.3.0")

# Tool: search
# FastMCP will derive the input schema from the annotated parameters.
@app.tool(name="search", description="Search music release groups by query; returns [{id,title,url}].")
async def search_tool(query: str) -> str:
    """
    Returns a JSON string: {"results":[{"id": "...","title":"...","url":"..."}]}
    """
    routed = route(query)
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
        results.append({
            "id": rgid,
            "title": f"{aname} — {title}",
            "url": f"https://musicbrainz.org/release-group/{rgid}",
        })
    return json.dumps({"results": results})

# Tool: fetch
@app.tool(name="fetch", description="Fetch full details for a release-group by ID; returns {id,title,text,url,metadata}.")
async def fetch_tool(id: str) -> str:
    """
    Returns a JSON string: {"id","title","text","url","metadata"}
    """
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
        "metadata": {"mb_release_group_id": id},
    }
    return json.dumps(doc)

if __name__ == "__main__":
    # SSE transport at /mcp (no host arg)
    port = int(os.getenv("PORT", "8000"))
    app.run(transport="sse", path="/mcp", port=port)
