const USE_CAA = true;
const MCP_URL = "/mcp";

const qInput   = document.getElementById("q");
const goBtn    = document.getElementById("go");
const vibeBtn  = document.getElementById("vibe");
const narrBtn  = document.getElementById("narrate");
const grid     = document.getElementById("grid");
const vibes    = document.getElementById("vibes");
const narrative= document.getElementById("narrative");

let lastVibePayload = null; // store the last vibe_board JSON for RAG

async function rpc(method, params, id = crypto.randomUUID()) {
  const res = await fetch(MCP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params })
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  if (data.error) throw new Error(data.error.message);
  return data;
}

function placeholderSVG(title) {
  const safe = (title || "No cover").replace(/&/g,"&amp;").replace(/</g,"&lt;");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600">
  <rect width="100%" height="100%" fill="#f3f3f3"/>
  <text x="50%" y="50%" text-anchor="middle" fill="#666" font-family="system-ui,sans-serif"
        font-size="28" font-weight="600" dominant-baseline="middle">${safe}</text>
  </svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

function candidateCAAUrlsForReleaseGroup(rgid) {
  const base = `https://coverartarchive.org/release-group/${rgid}`;
  return [`${base}/front-500`, `${base}/front-250`, `${base}/front`, `${base}/front?size=500`, `${base}/front?size=250`];
}

function attachCoverLoader(imgEl, rgid, title) {
  if (!USE_CAA) { imgEl.src = placeholderSVG(title); return; }
  const candidates = candidateCAAUrlsForReleaseGroup(rgid);
  let i = 0;
  const tryNext = () => {
    if (i >= candidates.length) { imgEl.src = placeholderSVG(title); imgEl.onerror=null; return; }
    imgEl.src = candidates[i++];
  };
  imgEl.onerror = () => tryNext();
  tryNext();
}

function cardHTML(item){
  const {id,title,url}=item;
  return `<div class="card" data-rgid="${id}" data-title="${encodeURIComponent(title)}" data-url="${url}">
    <img class="cover" alt="${title}" />
    <div class="meta"><div class="title">${title}</div>
    <div class="dim"><a href="${url}" target="_blank" rel="noopener">MusicBrainz</a></div></div></div>`;
}

function renderGrid(results){
  if(!results?.length){grid.innerHTML=`<div class="dim">No results.</div>`;return;}
  grid.innerHTML=results.map(cardHTML).join("");
  grid.querySelectorAll(".card").forEach(c=>{
    const rgid=c.dataset.rgid, title=decodeURIComponent(c.dataset.title||"");
    const img=c.querySelector("img.cover"); attachCoverLoader(img, rgid, title);
  });
}

async function doSearch(){
  const query=qInput.value.trim(); if(!query) return;
  lastVibePayload = null;
  narrative.style.display = "none";
  narrative.textContent = "";
  vibes.innerHTML=""; // clear vibe view when doing plain search
  grid.innerHTML=`<div class="dim">Searching “${query}”…</div>`;
  try{
    const data=await rpc("tools/call",{name:"search",arguments:{query}});
    const payload=JSON.parse(data?.result?.content?.[0]?.text||"{}");
    renderGrid(payload.results||[]);
  }catch(e){grid.innerHTML=`<div class="dim">Search failed.</div>`;}
}

// --- Vibe board UI ---
function swatchesHTML(hexes=[]) {
  return `<div class="swatches">${hexes.map(h=>`<span class="swatch" title="${h}" style="background:${h}"></span>`).join("")}</div>`;
}
function vibeItemCard(item){
  const { id, title, url, cover_url, palette_hex=[], mini_caption } = item;
  const img = cover_url || placeholderSVG(title);
  return `<div class="card">
    <img class="cover" src="${img}" alt="${title}" onerror="this.src='${placeholderSVG(title)}'"/>
    ${swatchesHTML(palette_hex)}
    <div class="meta">
      <div class="title">${title}</div>
      <div class="dim">${mini_caption||""}</div>
      <div class="dim"><a href="${url}" target="_blank" rel="noopener">MusicBrainz</a></div>
    </div>
  </div>`;
}
function renderVibeBoard(groups=[]) {
  vibes.innerHTML = groups.map(g => {
    const cards = g.items.map(vibeItemCard).join("");
    return `<section class="section">
      <h2>${g.label}</h2>
      <div class="summary">${g.summary}</div>
      <div class="grid">${cards}</div>
    </section>`;
  }).join("") || `<div class="dim" style="margin-top:16px">No vibe groups found.</div>`;
  grid.innerHTML = ""; // hide plain grid when showing vibes
}

async function buildVibeBoard(){
  const query=qInput.value.trim(); if(!query) return;
  narrative.style.display = "none";
  narrative.textContent = "";
  grid.innerHTML=""; vibes.innerHTML=`<div class="dim">Building vibe board for “${query}”…</div>`;
  try{
    const data=await rpc("tools/call",{name:"vibe_board",arguments:{query,limit:12}});
    const payload=JSON.parse(data?.result?.content?.[0]?.text||"{}"); // {query, groups:[...]}
    lastVibePayload = payload;
    renderVibeBoard(payload.groups||[]);
  }catch(e){
    console.error(e);
    vibes.innerHTML=`<div class="dim">Vibe board failed. See console.</div>`;
  }
}

// --- RAG: summarize vibe board with LLM ---
async function generateNarrative(){
  if(!lastVibePayload || !(lastVibePayload.groups||[]).length){
    alert("Build a vibe board first.");
    return;
  }
  narrative.style.display = "block";
  narrative.classList.add("dim");
  narrative.textContent = "Generating vibe narrative…";
  try{
    const jsonStr = JSON.stringify(lastVibePayload);
    const data = await rpc("tools/call", {
      name: "rag_summarize",
      arguments: { json: jsonStr, style: "poetic" }
    });
    const res = JSON.parse(data?.result?.content?.[0]?.text || "{}");
    if(res.error){
      narrative.textContent = `LLM error: ${res.error}`;
      return;
    }
    narrative.classList.remove("dim");
    narrative.textContent = res.summary || "(no summary)";
  }catch(e){
    narrative.textContent = "Narrative generation failed. Check console.";
    console.error(e);
  }
}

goBtn.onclick=doSearch;
vibeBtn.onclick=buildVibeBoard;
narrBtn.onclick=generateNarrative;
qInput.onkeydown=e=>{ if(e.key==="Enter"){ if (e.shiftKey) buildVibeBoard(); else doSearch(); } };
