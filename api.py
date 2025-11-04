# api.py
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from covers_core import search_cover_art_core, route

app = FastAPI(title="Covers API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "null"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/api/search")
async def search(
    query: str = Query(..., min_length=1),
    limit: int = 8,
    debug: int = 0
):
    routed = route(query)
    data = await search_cover_art_core(query, limit, debug=bool(debug))
    return {
        "query": query,
        "routed": routed,
        "results": data["results"],
        **({"debug": data["debug"]} if debug else {})
    }
