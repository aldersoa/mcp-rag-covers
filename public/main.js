// public/main.js

// Set to true to try real covers from Cover Art Archive.
// Leave false if you want only the SVG placeholder.
const USE_CAA = true;

const MCP_URL = "/mcp";
const qInput = document.getElementById("q");
const goBtn  = document.getElementById("go");
const grid   = document.getElementById("grid");

// ---------- JSON-RPC helper ----------
async function rpc(method, params, id = crypto.randomUUID()) {
  const res = await fetch(MCP_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json, text/event-stream"
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params })
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`RPC ${method} failed: ${res.status} ${txt}`);
  }
  const data = await res.json();
  if (data.error) throw new Error(`RPC error: ${data.error.code} ${data.error.message}`);
  return data;
}

// ---------- UI helpers ----------
function placeholderSVG(title) {
  const safe = (title || "No cover").replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="600" height="600">
      <defs>
        <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#f3f3f3"/>
          <stop offset="100%" stop-color="#e1e1e1"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#g)"/>
      <text x="50%" y="50%" text-anchor="middle" fill="#666" font-family="system-ui, sans-serif"
            font-size="28" font-weight="600" dominant-baseline="middle">${safe}</text>
    </svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

// Build a list of candidate CAA URLs to try for a release-group.
// Some RGs only have certain sizes; some only work with the query param form.
function candidateCAAUrlsForReleaseGroup(rgid) {
  const base = `https://coverartarchive.org/release-group/${rgid}`;
  return [
    `${base}/front-500`,
    `${base}/front-250`,
    `${base}/front`,
    `${base}/front?size=500`,
    `${base}/front?size=250`,
  ];
}

// Tries each candidate URL in order; on error, advances to the next.
// If none succeed, falls back to the SVG placeholder.
function attachCoverLoader(imgEl, rgid, title) {
  if (!USE_CAA) {
    imgEl.src = placeholderSVG(title);
    return;
  }
  const candidates = candidateCAAUrlsForReleaseGroup(rgid);
  let i = 0;

  const tryNext = () => {
    if (i >= candidates.length) {
      imgEl.src = placeholderSVG(title);
      imgEl.onerror = null;
      return;
    }
    imgEl.src = candidates[i++];
  };

  imgEl.onerror = () => tryNext();
  tryNext(); // start
}

function cardHTML(item) {
  const { id, title, url } = item;
  // data-* used for wiring the loader + click handler later
  return `
    <div class="card" data-rgid="${id}" data-title="${encodeURIComponent(title)}" data-url="${url}">
      <img class="cover" alt="${title}" />
      <div class="meta">
        <div class="title">${title}</div>
        <div class="dim"><a href="${url}" target="_blank" rel="noopener">MusicBrainz</a></div>
      </div>
    </div>
  `;
}

function renderGrid(results) {
  if (!results || results.length === 0) {
    grid.innerHTML = `<div class="dim">No results. Try a simpler query (e.g., "Radiohead" or "tag:jazz").</div>`;
    return;
  }
  grid.innerHTML = results.map(cardHTML).join("");

  // Wire up images and click handlers
  grid.querySelectorAll(".card").forEach(card => {
    const rgid  = card.getAttribute("data-rgid");
    const title = decodeURIComponent(card.getAttribute("data-title") || "");
    const img   = card.querySelector("img.cover");

    // Load image (CAA cascade or placeholder)
    attachCoverLoader(img, rgid, title);

    // Click = fetch details (avoid hijacking link clicks)
    card.addEventListener("click", async (e) => {
      if (e.target.tagName.toLowerCase() === "a") return;
      try {
        const data = await rpc("tools/call", { name: "fetch", arguments: { id: rgid } });
        const payloadJSON = data?.result?.content?.[0]?.text || "{}";
        const doc = JSON.parse(payloadJSON);
        const msg = [
          doc.title || "(untitled)",
          "",
          (doc.text || "").slice(0, 800) + ((doc.text || "").length > 800 ? "…" : ""),
          "",
          doc.url || ""
        ].join("\n");
        alert(msg);
      } catch (err) {
        console.error(err);
        alert("Failed to fetch details for this release-group.");
      }
    });
  });
}

// ---------- Search flow ----------
async function doSearch() {
  const query = (qInput.value || "").trim();
  if (!query) return;
  grid.innerHTML = `<div class="dim">Searching “${query}”…</div>`;
  try {
    const data = await rpc("tools/call", { name: "search", arguments: { query } }, "s1");
    const payloadJSON = data?.result?.content?.[0]?.text || "{}";
    const payload = JSON.parse(payloadJSON); // { results: [...] }
    renderGrid(payload.results || []);
  } catch (err) {
    console.error(err);
    grid.innerHTML = `<div class="dim">Search failed. Check the server logs and ensure /mcp is reachable.</div>`;
  }
}

goBtn.addEventListener("click", doSearch);
qInput.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });

// Optional: prefill and auto-search for quick testing
// qInput.value = "Radiohead"; doSearch();
