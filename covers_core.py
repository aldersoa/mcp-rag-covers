# covers_core.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import re
import httpx
import certifi

# ---- Constants ---------------------------------------------------------------

MB = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org"
ITUNES = "https://itunes.apple.com/search"
UA = {"User-Agent": "covers-py/0.4 (demo)"}

# ---- HTTP client helper (force HTTP/1.1; use certifi for TLS) ---------------

def _client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=UA,
        timeout=timeout,
        verify=certifi.where(),
        http2=False,  # your network was flaky with HTTP/2; stick to 1.1
    )

# ---- Tiny "RAG" router -------------------------------------------------------

def route(prompt: str) -> Dict[str, Any]:
    """
    Interpret the prompt and return a structured route.
    - If the user says 'by <artist>' or 'from <artist>', force artist mode.
    - If the user mentions a genre + 'covers'/'bands', prefer tag mode.
    - Otherwise detect genre by word boundary, else treat as artist.
    """
    p = prompt.lower().strip()

    # explicit artist phrases -> force artist path
    m = re.search(r"\b(from|by)\s+([a-z0-9 .'\-]+)$", p)
    if m:
        return {"type": "artist", "value": m.group(2).strip(), "force_artist": True}

    genres = [
        "metal", "death metal", "black metal", "thrash metal", "doom metal",
        "rock", "punk", "hip hop", "jazz", "electronic", "classical", "pop",
    ]

    # prefer tag path when prompt says "<genre> ... covers/bands"
    for g in genres:
        if re.search(rf"\b{re.escape(g)}\b", p) and ("band" in p or "covers" in p):
            return {"type": "tag", "value": g, "force_tag": True}

    # plain genre mention
    for g in genres:
        if re.search(rf"\b{re.escape(g)}\b", p):
            return {"type": "tag", "value": g}

    # fallback: artist
    return {"type": "artist", "value": prompt}

# ---- MusicBrainz helpers -----------------------------------------------------

async def mb_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with _client(20) as s:
            r = await s.get(f"{MB}/{path}", params={**params, "fmt": "json"})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError:
        return {}

async def search_artists_by_query(q: str, limit: int = 3) -> List[Dict[str, Any]]:
    j = await mb_get("artist", {"query": q, "limit": limit})
    return j.get("artists", []) or []

async def search_artists_by_tag(tag: str, limit: int = 5) -> List[Dict[str, Any]]:
    j = await mb_get("artist", {"query": f"tag:{tag}", "limit": limit})
    return j.get("artists", []) or []

async def release_groups_for_artist(artist_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    # Use release-groups (album/ep). Add 'single' if you want singles too.
    j = await mb_get("release-group", {
        "artist": artist_id,
        "type": "album|ep",
        "limit": limit
    })
    return j.get("release-groups", []) or []

# ---- Cover lookups -----------------------------------------------------------

async def cover_from_caa_release_group(rg_id: str) -> Optional[str]:
    """Prefer CAA release-group art (often has 'front' image)."""
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
    """Fallback art via iTunes Search API (no key required)."""
    q = f"{artist} {album}".strip()
    try:
        async with _client(8) as s:
            r = await s.get(ITUNES, params={
                "term": q,
                "media": "music",
                "entity": "album",
                "limit": 1
            })
            if r.status_code != 200:
                return None
            j = r.json()
            if not j.get("results"):
                return None
            art = j["results"][0].get("artworkUrl100")
            if not art:
                return None
            # Up-size the default 100x100
            return art.replace("100x100bb", "600x600bb")
    except httpx.HTTPError:
        return None

# ---- Main search -------------------------------------------------------------

async def search_cover_art_core(query: str, limit: int = 8, debug: bool = False) -> Dict[str, Any]:
    """
    Stateless search. Returns dict: {"results":[...], "debug":{...}?}
    - Picks ONE best artist (prevents bleed between artists).
    - Uses release-groups; prefers CAA, falls back to iTunes.
    - Hard-caps returned items to `limit`.
    """
    routed = route(query)
    results: List[Dict[str, Any]] = []

    # --- Choose ONE artist only ------------------------------------------------
    artists: List[Dict[str, Any]] = []

    if routed.get("force_artist"):
        # explicit "by <artist>" / "from <artist>"
        matches = await search_artists_by_query(routed["value"], limit=5)
        exact = [a for a in matches if a.get("name", "").lower() == routed["value"].lower()]
        artists = (exact or matches)[:1]   # pick top-1
    else:
        # try raw prompt, then routed-artist, then tag — always keep top-1
        raw = await search_artists_by_query(query, limit=3)
        artists = raw[:1]
        if not artists and routed["type"] == "artist" and routed["value"] != query:
            ra = await search_artists_by_query(routed["value"], limit=3)
            artists = ra[:1]
        if not artists and routed["type"] == "tag":
            ta = await search_artists_by_tag(routed["value"], limit=5)
            artists = ta[:1]

    if not artists:
        return {"results": results, "debug": {"routed": routed} if debug else None}

    # --- Fetch release-groups for that ONE artist only -------------------------
    artist = artists[0]
    aid, aname = artist["id"], artist["name"]
    rgs = await release_groups_for_artist(aid, limit=max(1, min(limit, 24)))

    # --- Build results, capped to `limit` -------------------------------------
    for rg in rgs:
        if len(results) >= limit:  # hard cap
            break
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
                "coverUrl": cover,
            })

    return {
        "results": results[:limit],  # belt & suspenders
        "debug": {"routed": routed, "artist": {"id": aid, "name": aname}} if debug else None,
    }
