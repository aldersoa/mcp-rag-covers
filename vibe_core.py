# vibe_core.py
import io, colorsys, asyncio, os
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans
import httpx

CAA_BASE = "https://coverartarchive.org"
MB_WS    = "https://musicbrainz.org/ws/2"
MB_UA    = os.getenv("MB_USER_AGENT", "covers-mcp/0.3.0 (contact@example.com)")

def caa_candidates_for_release_group(rgid: str) -> List[str]:
    b = f"{CAA_BASE}/release-group/{rgid}"
    return [
        f"{b}/front-500",
        f"{b}/front-250",
        f"{b}/front",
        f"{b}/front?size=500",
        f"{b}/front?size=250",
    ]

def caa_candidates_for_release(relid: str) -> List[str]:
    b = f"{CAA_BASE}/release/{relid}"
    return [
        f"{b}/front-500",
        f"{b}/front-250",
        f"{b}/front",
        f"{b}/front?size=500",
        f"{b}/front?size=250",
    ]

async def find_first_working_url(client: httpx.AsyncClient, urls: List[str]) -> Optional[str]:
    """
    With follow_redirects=True on the client, a successful image request will end as 200.
    We accept any 2xx code as success.
    """
    for u in urls:
        try:
            r = await client.get(u, timeout=12)
            if 200 <= r.status_code < 300 and r.content:
                return str(r.url)  # final resolved URL after redirects
        except Exception:
            pass
    return None

async def fetch_image(client: httpx.AsyncClient, url: str) -> Optional[Image.Image]:
    try:
        r = await client.get(url, timeout=15)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None

async def mb_get_releases_for_group(client: httpx.AsyncClient, rgid: str, limit: int = 10) -> List[str]:
    try:
        r = await client.get(
            f"{MB_WS}/release",
            params={"release-group": rgid, "limit": limit, "fmt": "json"},
            headers={"User-Agent": MB_UA, "Accept": "application/json"},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        rels = data.get("releases") or []
        return [rel.get("id") for rel in rels if rel.get("id")]
    except Exception:
        return []

async def find_cover_for_group_or_releases(client: httpx.AsyncClient, rgid: str) -> Dict[str, str]:
    # 1) Try RG art
    rg_url = await find_first_working_url(client, caa_candidates_for_release_group(rgid))
    if rg_url:
        return {"url": rg_url, "source": "rg"}

    # 2) Try multiple releases
    rel_ids = await mb_get_releases_for_group(client, rgid, limit=10)
    for relid in rel_ids:
        rel_url = await find_first_working_url(client, caa_candidates_for_release(relid))
        if rel_url:
            return {"url": rel_url, "source": f"release:{relid}"}

    return {}

def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    r, g, b = [max(0, min(255, int(x))) for x in rgb]
    return "#{:02x}{:02x}{:02x}".format(r, g, b)

def image_palette_and_stats(im: Image.Image, k: int = 4) -> Dict[str, Any]:
    im_small = im.resize((128, 128))
    arr = np.asarray(im_small).reshape(-1, 3).astype(np.float32)

    km = KMeans(n_clusters=k, n_init=4, random_state=0)
    km.fit(arr)
    centers = km.cluster_centers_
    palette_rgb = [tuple(map(float, c)) for c in centers]
    palette_hex = [rgb_to_hex(c) for c in palette_rgb]

    rgb_norm = arr / 255.0
    hsv = np.array([colorsys.rgb_to_hsv(*px) for px in rgb_norm])
    h_mean = float(np.mean(hsv[:, 0]))
    s_mean = float(np.mean(hsv[:, 1]))
    v_mean = float(np.mean(hsv[:, 2]))

    vibe_words = []
    vibe_words.append("warm" if h_mean < 0.15 or h_mean > 0.85 else ("cool" if 0.45 < h_mean < 0.75 else "neutral"))
    vibe_words.append("saturated" if s_mean > 0.45 else "muted")
    vibe_words.append("bright" if v_mean > 0.6 else ("dark" if v_mean < 0.35 else "midtone"))
    caption = f"{', '.join(vibe_words)} palette"

    return {
        "palette_hex": palette_hex,
        "hsv_mean": {"h": h_mean, "s": s_mean, "v": v_mean},
        "caption": caption,
    }

def group_label(stats_list: List[Dict[str, Any]]) -> str:
    if not stats_list:
        return "Mixed"
    h = np.mean([s["hsv_mean"]["h"] for s in stats_list])
    s = np.mean([s["hsv_mean"]["s"] for s in stats_list])
    v = np.mean([s["hsv_mean"]["v"] for s in stats_list])

    hue_name = "Warm" if h < 0.15 or h > 0.85 else ("Cool" if 0.45 < h < 0.75 else "Neutral")
    sat_name = "Saturated" if s > 0.45 else "Muted"
    val_name = "Bright" if v > 0.6 else ("Dark" if v < 0.35 else "Midtone")
    return f"{hue_name} · {sat_name} · {val_name}"

def group_summary(label: str, count: int) -> str:
    parts = [p.strip() for p in label.split("·")]
    tone = []
    if "Warm" in parts[0]: tone.append("reds/oranges")
    elif "Cool" in parts[0]: tone.append("blues/greens")
    else: tone.append("balanced hues")
    if "Saturated" in parts[1]: tone.append("rich color blocks")
    else: tone.append("soft, desaturated tones")
    if "Bright" in parts[2]: tone.append("high-key, airy feel")
    elif "Dark" in parts[2]: tone.append("low-key, moody feel")
    else: tone.append("even midtones")
    return f"{count} covers leaning toward {', '.join(tone)}."

async def build_vibe_board(items: List[Dict[str, Any]], max_items: int = 12, debug: bool = False) -> Dict[str, Any]:
    feats: List[Dict[str, Any]] = []
    dbg: List[Dict[str, Any]] = []

    headers = {"User-Agent": MB_UA, "Accept": "application/json, image/*"}

    # ✅ follow_redirects=True is the key change
    async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
        sem = asyncio.Semaphore(6)

        async def process(item):
            async with sem:
                rgid = item["id"]

                found = await find_cover_for_group_or_releases(client, rgid)
                if not found:
                    if debug:
                        dbg.append({"rgid": rgid, "title": item.get("title"), "hit": False, "reason": "no_caa_rg_or_release"})
                    return None

                img_url = found["url"]
                im = await fetch_image(client, img_url)
                if not im:
                    if debug:
                        dbg.append({"rgid": rgid, "title": item.get("title"), "hit": False, "reason": "fetch_failed", "src": found.get("source")})
                    return None

                stats = image_palette_and_stats(im, k=4)
                if debug:
                    dbg.append({"rgid": rgid, "title": item.get("title"), "hit": True, "src": found.get("source"), "url": img_url})

                return {
                    "id": rgid,
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "cover_url": img_url,
                    "palette_hex": stats["palette_hex"],
                    "hsv_mean": stats["hsv_mean"],
                    "mini_caption": stats["caption"],
                }

        tasks = [process(x) for x in items[:max_items]]
        for r in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(r, Exception):
                if debug:
                    dbg.append({"error": str(r)})
                continue
            if r:
                feats.append(r)

    if not feats:
        return {"groups": [], **({"debug": dbg} if debug else {})}

    X = np.array([[f["hsv_mean"]["h"], f["hsv_mean"]["s"], f["hsv_mean"]["v"]] for f in feats])
    km = KMeans(n_clusters=2, n_init=8, random_state=42).fit(X)
    labels = km.labels_

    grouped: Dict[int, List[Dict[str, Any]]] = {0: [], 1: []}
    for f, lab in zip(feats, labels):
        grouped[int(lab)].append(f)

    results = []
    for gi in sorted(grouped.keys()):
        gitems = grouped[gi]
        glabel = group_label(gitems)
        gsum = group_summary(glabel, len(gitems))
        results.append({"label": glabel, "summary": gsum, "items": gitems})

    payload = {"groups": results}
    if debug:
        payload["debug"] = dbg
    return payload
