import os, httpx
from typing import Any, Dict, List, Optional

MB_WS = "https://musicbrainz.org/ws/2"
MB_UA = os.getenv("MB_USER_AGENT", "covers-mcp/0.2.0 (contact@example.com)")

def route(q: str) -> Dict[str, str]:
    q = (q or "").strip()
    if q.lower().startswith("tag:"):
        return {"type": "tag", "value": q.split(":", 1)[1].strip()}
    if q.startswith("#"):
        return {"type": "tag", "value": q[1:].strip()}
    return {"type": "artist", "value": q}

async def _get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0, headers={
        "User-Agent": MB_UA, "Accept": "application/json"}) as c:
        params = {**params, "fmt": "json"}
        r = await c.get(f"{MB_WS}/{path}", params=params)
        r.raise_for_status()
        return r.json()

async def mb_get(kind: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        if kind == "release-group" and "id" in params:
            return await _get(f"release-group/{params['id']}", {})
        return await _get(kind, params)
    except httpx.HTTPError:
        return None

async def search_artists_by_query(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        d = await _get("artist", {"query": query, "limit": limit})
        return [{"id": a.get("id"), "name": a.get("name")} for a in d.get("artists", []) if a.get("id")]
    except httpx.HTTPError:
        return []

async def search_artists_by_tag(tag: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        d = await _get("artist", {"tag": tag, "limit": limit})
        return [{"id": a.get("id"), "name": a.get("name")} for a in d.get("artists", []) if a.get("id")]
    except httpx.HTTPError:
        return []

async def release_groups_for_artist(aid: str, limit: int = 25) -> List[Dict[str, Any]]:
    try:
        d = await _get("release-group", {"artist": aid, "limit": limit})
        return [{"id": rg.get("id"), "title": rg.get("title")} for rg in d.get("release-groups", []) if rg.get("id")]
    except httpx.HTTPError:
        return []
