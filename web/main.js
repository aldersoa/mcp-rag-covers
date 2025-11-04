const API_BASE = "http://127.0.0.1:8787/api/search";

const input = document.getElementById("q");
const btn   = document.getElementById("go");
const grid  = document.getElementById("grid");

async function search(query) {
  grid.textContent = "Loading…";
  try {
    const url = API_BASE + "?" + new URLSearchParams({ query, limit: 8, debug: 0 });
    console.log("[UI] GET", url);
    const r = await fetch(url);
    const j = await r.json();
    console.log("[UI] response", j);

    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    if (j.error) throw new Error(j.error);

    render(j.results || []);
  } catch (e) {
    console.error("Search error:", e);
    grid.innerHTML = `<div style="color:#b00">${e.message || e}</div>`;
  }
}

function render(items) {
  grid.innerHTML = "";

  const header = document.createElement("div");
  header.style.marginBottom = "8px";
  header.textContent = `Results: ${items.length}`;
  grid.appendChild(header);

  if (!items.length) {
    const empty = document.createElement("div");
    empty.textContent = "No results.";
    grid.appendChild(empty);
    return;
  }

  for (const item of items) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img class="cover" src="${esc(item.coverUrl)}" alt="cover" loading="lazy"/>
      <div class="meta">
        <div class="title">${esc(item.releaseTitle)}</div>
        <div class="dim">${esc(item.artist)}${item.releaseDate ? " • " + esc(item.releaseDate) : ""}</div>
      </div>
    `;
    // Help debug broken images
    const img = card.querySelector("img");
    img.addEventListener("error", () => {
      img.replaceWith(Object.assign(document.createElement("div"), {
        textContent: "Image failed to load",
        style: "height:160px;display:flex;align-items:center;justify-content:center;background:#f3f3f3;border-radius:8px;"
      }));
    });

    grid.appendChild(card);
  }
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, m => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;" }[m]));
}

btn.addEventListener("click", () => search(input.value || "show me covers from metallica"));
input.addEventListener("keydown", (e) => { if (e.key === "Enter") btn.click(); });

// Run a demo search on load
search("show me covers from metallica");
