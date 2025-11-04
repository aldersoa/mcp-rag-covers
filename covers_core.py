# covers_core.py
from typing import List, Dict, Any, Optional, Tuple
import re
import httpx
import certifi

MB = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org"
ITUNES = "https://itunes.apple.com/search"
UA  = {"User-Agent": "covers-py/0.3 (demo)"}

def _client(timeout=20):
    # Force HTTP/1.1 (your network RSTs some HTTP/2 handshakes).
    return httpx.AsyncClient(
        headers=UA,
        timeout=timeout,
        verify=certifi.where(),
        http2=False
    )

# ---------- tiny "RAG" router ----------
def route(prompt: str) -> Dict[str, str]:
    p = prompt.lower().strip()
    # explicit artist phrases
    m = re.search(r"\b(from|by)\s+([a-z0-9 .'\-]+)$", p)
    if m:
        return {"type": "artist", "value": m.group(2).strip()}
    # genre with word boundaries
    genres = [
        "metal","death metal","black metal","thrash metal","doom metal",
        "rock","punk","hip hop","jazz","electronic","classical","pop"
    ]
    for g in genres:
        if re.search(rf"\b{re.escape(g)}\b", p):
            return {"type": "tag", "value": g}
    # fallback: treat whole prompt as artist
    return {"type": "artist", "value": prompt}

# ---------- MB helpers ----------
async def mb_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with _client(20) as s:
            r = await s.get(f"{MB}/{path}", params={**params, "fmt": "json"})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError:
        return {}

async def search_artists_by_query(q: str, limit=3) -> List[Dict[str, Any]]:
    j = await mb_get("artist", {"query": q, "limit": limit})
    return j.get("artists", []) or []

async def search_artists_by_tag(tag: str, limit=5) -> List[Dict[str, Any]]:
    j = await mb_get("artist", {"query": f"tag:{tag}", "limit": limit})
    return j.get("artists", []) or []

async def release_groups_for_artist(artist_id: str, limit=12) -> List[Dict[str, Any]]:
    # Use release-groups (album/ep/single) — CAA has front art at this level.
    # You can tweak 'type' to include 'single' if desired.
    j = await mb_get("release-group", {
        "artist": artist_id,
        "type": "album|ep",
        "limit": limit
    })
    return j.get("release-groups", []) or []

# ---------- cover sources ----------
async def cover_from_caa_release_group(rg_id: str) -> Optional[str]:
    # Prefer release-group endpoint for better coverage
    try:
        async with _client(12) as s:
            r = await s.get(f"{CAA}/release-group/{rg_id}")
            if r.status_code != 200:
                return None
            data = r.json()
            for img in data.get("images", []):
                if img.get("front") is True and img.get("image"):
                    return img["image"]
    except httpx.HTTPError:
        return None
    return None

async def cover_from_itunes(artist: str, album: str) -> Optional[str]:
    # Fallback art (no key needed). Upsize 100x100 -> 600x600.
    q = f"{artist} {album}".strip()
    try:
        async with _client(8) as s:
            r = await s.get(ITUNES, params={
                "term": q, "media": "music", "entity": "album", "limit": 1
            })
            if r.status_code != 200:
                return None
            j = r.json()
            if not j.get("results"):
                return None
            art = j["results"][0].get("artworkUrl100")
            if not art:
                return None
            return art.replace("100x100bb", "600x600bb")
    except httpx.HTTPError:
        return None

# ---------- main search ----------
async def search_cover_art_core(query: str, limit: int = 8, debug: bool = False) -> Dict[str, Any]:
    """
    Returns a dict: {"results": [...], "debug": {...}}
    results items: {artist, releaseTitle, releaseDate?, coverUrl}
    """
    routed = route(query)
    dbg: Dict[str, Any] = {"routed": routed}

    # 0) Try raw prompt as artist
    artists = await search_artists_by_query(query, limit=3)
    dbg["artists_raw"] = [{"id": a["id"], "name": a["name"]} for a in artists][:5]

    # 1) If empty, try routed artist
    if not artists and routed["type"] == "artist" and routed["value"] != query:
        artists = await search_artists_by_query(routed["value"], limit=3)
        dbg["artists_routed"] = [{"id": a["id"], "name": a["name"]} for a in artists][:5]

    # 2) If still empty, try tag
    if not artists and routed["type"] == "tag":
        artists = await search_artists_by_tag(routed["value"], limit=5)
        dbg["artists_tag"] = [{"id": a["id"], "name": a["name"]} for a in artists][:5]

    results: List[Dict[str, Any]] = []
    if not artists:
        return {"results": results, "debug": dbg if debug else None}

    # Collect release-groups, then covers (CAA -> iTunes fallback)
    for a in artists:
        aid, aname = a["id"], a["name"]
        rgs = await release_groups_for_artist(aid, limit=min(limit, 12))
        dbg.setdefault("rgs_counts", []).append((aname, len(rgs)))
        for rg in rgs:
            rgid = rg["id"]
            title = rg.get("title", "Untitled")
            firstdate = rg.get("first-release-date")
            cover = await cover_from_caa_release_group(rgid)
            if not cover:
                cover = await cover_from_itunes(aname, title)
            if cover:
                results.append({
                    "artist": aname,
                    "releaseTitle": title,
                    "releaseDate": firstdate,
                    "coverUrl": cover
                })

    return {"results": results, "debug": dbg if debug else None}
