import os
import httpx
from typing import List, Dict, Any, Optional

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "").strip()  # e.g. http://localhost:11434
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.2").strip() or "llama3.2"

SYSTEM_PROMPT = (
    "You are a concise, evocative curator of album-art mood boards. "
    "Given clustered groups with color palettes and short captions, write a single paragraph (80–140 words) "
    "that captures the overall vibe. Mention contrasts between groups when relevant. Avoid track lists; "
    "focus on atmosphere, palette, and era feelings."
)

def _messages_from(board_json: str, style: str) -> List[Dict[str, str]]:
    style_note = f"Write in a {style} style." if style else "Write in a neutral, evocative style."
    user_prompt = (
        f"{style_note}\n\n"
        f"Input JSON (vibe_board):\n{board_json}\n\n"
        "Return only the paragraph, no preamble, no markdown headers."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

async def call_openai(board_json: str, style: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    msgs = _messages_from(board_json, style)
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": msgs,
        "temperature": 0.7,
        "max_tokens": 220,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

async def call_ollama(board_json: str, style: str) -> str:
    if not OLLAMA_HOST:
        raise RuntimeError("OLLAMA_HOST not set")
    msgs = _messages_from(board_json, style)
    url = f"{OLLAMA_HOST.rstrip('/')}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": msgs,
        "stream": False,
        "options": {"temperature": 0.7},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        # Ollama response shape: {"message":{"content": "..."}}
        # or {"messages":[...]} depending on version. Handle both:
        if "message" in data and "content" in data["message"]:
            return data["message"]["content"].strip()
        if "messages" in data and data["messages"]:
            return data["messages"][-1].get("content", "").strip()
        raise RuntimeError("Unexpected Ollama response format")

async def summarize_vibe(board_json: str, style: str = "") -> str:
    """
    Decide backend and return a single-paragraph narrative.
    Priority: OpenAI if key is set; else Ollama if host is set; else error.
    """
    if OPENAI_API_KEY:
        return await call_openai(board_json, style)
    if OLLAMA_HOST:
        return await call_ollama(board_json, style)
    raise RuntimeError(
        "No LLM backend configured. Set OPENAI_API_KEY (and optional OPENAI_MODEL) "
        "or set OLLAMA_HOST (and optional OLLAMA_MODEL)."
    )
