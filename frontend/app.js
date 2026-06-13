// MuleNet frontend — REQUIREMENTS.md §13 (Owner: P4).
// Renders the transaction graph + ring list; click a ring to inspect and draft a SAR.

const $ = (id) => document.getElementById(id);
let network = null;

function riskColor(r) {
  if (r >= 0.66) return "#ff5a5f";
  if (r >= 0.33) return "#e3b341";
  return "#3a4756";
}

async function loadGraph() {
  const g = await fetch("/api/graph").then((r) => r.json());
  const nodes = g.nodes.map((n) => ({
    id: n.id, label: n.id, value: 4 + n.risk * 20,
    color: { background: riskColor(n.risk), border: "#0e1116" },
    font: { color: "#c9d1d9", size: 11 },
  }));
  const edges = g.edges.map((e) => ({
    id: e.id, from: e.source, to: e.target, arrows: "to",
    color: { color: e.suspicious ? "#ff5a5f" : "#30363d", opacity: e.suspicious ? 0.9 : 0.35 },
  }));
  const data = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
  const options = {
    physics: { stabilization: true, barnesHut: { gravitationalConstant: -8000, springLength: 120 } },
    interaction: { hover: true },
    nodes: { shape: "dot" },
  };
  network = new vis.Network($("graph"), data, options);
  network.on("click", (p) => { if (p.nodes.length) showAccount(p.nodes[0]); });
}

async function loadSummary() {
  const s = await fetch("/api/dataset/current").then((r) => r.json());
  $("summary").textContent =
    `${s.accounts} accounts · ${s.transactions} txns · ${s.rings_detected} rings · ${s.flagged_accounts} flagged`;
}

async function loadEval() {
  const e = await fetch("/api/eval").then((r) => r.json());
  $("eval").innerHTML =
    `<div class="big">${Math.round(e.ring_recall * 100)}%</div> ring-recall ` +
    `(${e.rings_matched}/${e.rings_true} planted rings found)<br/>` +
    `account precision ${e.account.precision} · recall ${e.account.recall} · ` +
    `F1 ${e.account.f1}<br/><span style="color:#8b949e">${e.false_positive_rings} false-positive rings</span>`;
}

async function loadRings() {
  const rings = await fetch("/api/rings").then((r) => r.json());
  $("rings").innerHTML = rings.length ? "" : "<span style='color:#8b949e'>no rings yet — detectors are stubs</span>";
  for (const r of rings) {
    const div = document.createElement("div");
    div.className = "ring";
    div.innerHTML =
      `<span class="score">${(r.score * 100).toFixed(0)}</span>` +
      `<span class="rid">${r.ring_id}</span>` +
      `<div class="meta">${r.account_ids.length} accounts · ${r.patterns.join(", ")}</div>`;
    div.onclick = () => showRing(r.ring_id);
    $("rings").appendChild(div);
  }
}

async function showRing(id) {
  const r = await fetch(`/api/rings/${id}`).then((x) => x.json());
  const d = $("detail");
  d.classList.remove("hidden");
  d.innerHTML =
    `<h2>${r.ring_id} <span class="score">${(r.score * 100).toFixed(0)}</span></h2>` +
    r.patterns.map((p) => `<span class="pill">${p}</span>`).join("") +
    `<p>${r.account_ids.length} accounts · ${r.tx_ids.length} transactions</p>` +
    `<button id="sarbtn">🧾 Generate SAR</button>` +
    `<pre id="sarout">key accounts: ${r.key_accounts.join(", ")}</pre>`;
  $("sarbtn").onclick = async () => {
    $("sarout").textContent = "drafting SAR…";
    const out = await fetch(`/api/rings/${id}/sar`, { method: "POST" }).then((x) => x.json());
    $("sarout").textContent = out.narrative + `\n\n[source: ${out.source || "ai"}]`;
  };
  if (network) network.selectNodes(r.account_ids.filter((a) => network.body.nodes[a]));
}

async function showAccount(id) {
  const a = await fetch(`/api/accounts/${id}`).then((x) => x.json());
  const d = $("detail");
  d.classList.remove("hidden");
  d.innerHTML =
    `<h2>${id} <span class="score">${(a.risk * 100).toFixed(0)}</span></h2>` +
    `<p>${a.account.owner_name} · ${a.account.account_type} · ${a.account.country} · KYC ${a.account.kyc_risk}</p>` +
    `<p>${a.findings.length} findings · ${a.transactions.length} transactions</p>` +
    a.findings.map((f) => `<span class="pill">${f.detector} ${(f.score * 100).toFixed(0)}</span>`).join("");
}

async function refresh() { await Promise.all([loadGraph(), loadSummary(), loadEval(), loadRings()]); }

$("gen").onclick = async () => {
  $("summary").textContent = "generating…";
  await fetch("/api/dataset/generate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  });
  await refresh();
};

refresh();
