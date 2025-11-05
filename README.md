## Overview

A lightweight **MCP server** that lets you:
- 🔍 Search MusicBrainz for release groups  
- 🎨 Build a color-clustered **Vibe Board** from Cover Art Archive images  
- 🧠 (Optionally) Summarize that vibe board with an **LLM** (OpenAI *or* free local **Ollama**)

It also serves a small web UI at **http://localhost:8000** where you can search, visualize covers, and generate a short narrative.

---

## Features
- **MCP Tools:** `search`, `fetch`, `vibe_board`, `rag_summarize`
- **Smart art retrieval:** tries both release-group and release-level art
- **Color analysis:** K-Means palette clustering and HSV statistics
- **Optional RAG:** summarize visual clusters using OpenAI or Ollama

---

## Requirements
- Python **3.10+**
- macOS / Linux / Windows (PowerShell)
- Internet access (for MusicBrainz + CAA)
- Optional: [Ollama](https://ollama.com) for free local LLMs

---

## Quick Start

### 1. Create and activate a virtual environment
~~~bash
python3 -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .\\.venv\\Scripts\\Activate.ps1
~~~

### 2. Install dependencies
~~~bash
pip install -r requirements.txt
~~~

### 3. Set environment variables

#### Required: MusicBrainz user agent
~~~bash
export MB_USER_AGENT="covers-mcp/0.4.0 (you@example.com)"
~~~

> MusicBrainz requires a valid, identifying `User-Agent` with contact info.

#### Optional: Choose your LLM backend

**A. OpenAI (paid, cheapest model `gpt-4o-mini`)**
~~~bash
export OPENAI_API_KEY="sk-...yourkey..."
export OPENAI_MODEL="gpt-4o-mini"     # optional
~~~

**B. Ollama (free, local)**
~~~bash
# 1. Install and start Ollama: https://ollama.com
ollama pull llama3.2
# 2. Point the server at it:
export OLLAMA_HOST="http://localhost:11434"
export OLLAMA_MODEL="llama3.2"        # optional
# Do NOT set OPENAI_API_KEY at the same time
~~~

### 4. Run the server
~~~bash
python server_http.py
~~~

Then open **http://localhost:8000**

Try:
1. Type an artist name (e.g. *Radiohead*)  
2. Click **Build Vibe Board**  
3. (Optional) Click **Generate Vibe Narrative**

---

## 🧪 CLI Tests (optional)

### Search
~~~bash
curl -s -X POST http://127.0.0.1:8000/mcp \
 -H "Content-Type: application/json" -H "Accept: application/json" \
 -d '{"jsonrpc":"2.0","id":"s1","method":"tools/call","params":{"name":"search","arguments":{"query":"Radiohead","limit":12}}}' \
 | jq -r '.result.content[0].text' | jq '.results | length'
~~~

### Vibe board
~~~bash
curl -s -X POST http://127.0.0.1:8000/mcp \
 -H "Content-Type: application/json" -H "Accept: application/json" \
 -d '{"jsonrpc":"2.0","id":"v1","method":"tools/call","params":{"name":"vibe_board","arguments":{"query":"Radiohead","limit":12,"debug":true}}}' \
 | jq -r '.result.content[0].text' | jq .
~~~

### Summarize (RAG generation)
~~~bash
# Create a vibe board
curl -s -X POST http://127.0.0.1:8000/mcp \
 -H "Content-Type: application/json" -H "Accept: application/json" \
 -d '{"jsonrpc":"2.0","id":"v1","method":"tools/call","params":{"name":"vibe_board","arguments":{"query":"Radiohead","limit":8}}}' \
 | jq -r '.result.content[0].text' > /tmp/vibe.json

# Summarize it with the LLM
jq -r '.' /tmp/vibe.json | \
xargs -0 -I{} bash -lc '
curl -s -X POST http://127.0.0.1:8000/mcp \
 -H "Content-Type: application/json" -H "Accept: application/json" \
 -d "{\\"jsonrpc\\":\\"2.0\\",\\"id\\":\\"v2\\",\\"method\\":\\"tools/call\\",\\"params\\":{\\"name\\":\\"rag_summarize\\",\\"arguments\\":{\\"json\\":$(printf %q "{}"),\\"style\\":\\"poetic\\"}}}" \
 | jq -r ".result.content[0].text" | jq .
'
~~~

---

## 🧠 What’s MCP? What’s RAG?

| Concept | Your server does it |
|----------|--------------------|
| **MCP** (Model Context Protocol) | ✅ JSON-RPC 2.0 endpoint `/mcp` with `tools/list` & `tools/call` |
| **Retrieval (R)** | ✅ Fetches release & cover data from MusicBrainz/CAA |
| **Analysis (A)** | ✅ Computes color clusters and mood labels |
| **Generation (G)** | ✅ via `rag_summarize` (OpenAI or Ollama) |
| **Full RAG pipeline** | ✅ Retrieval → Analysis → Generation |

---

## 🛠️ Troubleshooting

### “No vibe groups found”
- Try another artist (Beatles, Miles Davis)
- Ensure outbound access to MusicBrainz/CAA
- Confirm `follow_redirects=True` in `vibe_core.py`

### “LLM backend error: 429 Too Many Requests”
- Wait a minute and retry (rate-limit window)
- Reduce `limit` (6–8)
- For OpenAI: use `gpt-4o-mini` or switch to Ollama


