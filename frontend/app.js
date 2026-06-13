// MuleNet frontend — REQUIREMENTS.md §8/§13 (Owner: P4).
// Renders the transaction graph with risk colors + ring clusters, a click-through ring
// detail panel (evidence + transactions + SAR), the eval banner, and the "Ask MuleNet" copilot.

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const REPORTING_THRESHOLD = 10_000;
const eurFmt = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const eur2Fmt = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR", minimumFractionDigits: 2 });
const eur = (n) => eurFmt.format(n || 0);
const eur2 = (n) => eur2Fmt.format(n || 0);
const pct = (x) => `${Math.round((x || 0) * 100)}%`;
function fmtDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Stable, distinct color per ring (by score-rank order from /api/rings).
const RING_COLORS = ["#ff7b72", "#4da3ff", "#3fb950", "#d2a8ff", "#e3b341", "#ff9bce",
  "#56d4dd", "#f0883e", "#a5d6ff", "#7ee787", "#ffa657", "#bc8cff"];
let RING_COLOR = {}; // ring_id -> hex
function ringColor(id) { return RING_COLOR[id] || "#8b949e"; }
function riskColor(r) {
  if (r >= 0.66) return "#ff5a5f";
  if (r >= 0.33) return "#e3b341";
  return "#3a4756";
}

let network = null, nodesDS = null, edgesDS = null, lastGraph = null;
let activeRing = null, activeMembers = null;
let showAll = false;                 // declutter: focus view (rings + flagged) by default
let viewNodes = [], viewEdges = [];  // what's actually rendered, after filtering

// A node earns a spot in the focus view if it's in a ring or flagged (risk ≥ 0.5).
const inFocus = (n) => !!n.ring || n.risk >= 0.5;

// ── graph ─────────────────────────────────────────────────────────────────
async function loadGraph() {
  lastGraph = await fetch("/api/graph").then((r) => r.json());
  renderGraph();
}

// (Re)build the network from lastGraph, honoring the focus/show-all filter.
function renderGraph() {
  const keep = new Set();
  viewNodes = lastGraph.nodes.filter((n) => showAll || inFocus(n));
  viewNodes.forEach((n) => keep.add(n.id));
  viewEdges = lastGraph.edges.filter((e) =>
    keep.has(e.source) && keep.has(e.target) && (showAll || e.ring || e.suspicious));

  nodesDS = new vis.DataSet(viewNodes.map(nodeStyle));
  edgesDS = new vis.DataSet(viewEdges.map(edgeStyle));
  network = new vis.Network($("graph"), { nodes: nodesDS, edges: edgesDS }, {
    physics: { stabilization: { iterations: 200 },
               barnesHut: { gravitationalConstant: -12000, springLength: 140, springConstant: 0.04, avoidOverlap: 0.3 } },
    interaction: { hover: true, tooltipDelay: 100 },
    nodes: { shape: "dot", scaling: { min: 5, max: 40 } },
    edges: { smooth: { type: "continuous" }, width: 1 },
  });
  network.on("click", (p) => { if (p.nodes.length) showAccount(p.nodes[0]); });
  network.on("doubleClick", (p) => {
    const n = lastGraph.nodes.find((x) => x.id === p.nodes[0]);
    if (n && n.ring) showRing(n.ring);
  });
  const nc = $("nodecount");
  if (nc) nc.textContent = `${viewNodes.length}${showAll ? "" : " key"} nodes`;
  if (activeMembers) highlightGraph([...activeMembers]);  // survive a re-render
}

// Labels are hidden by default (clutter); the hover tooltip carries the id.
function nodeStyle(n) {
  const inRing = !!n.ring, flagged = n.risk >= 0.5;
  const value = inRing ? 22 + n.risk * 26 : flagged ? 12 + n.risk * 18 : 3 + n.risk * 6;
  return {
    id: n.id, label: "", value,
    title: `${n.id} · risk ${pct(n.risk)}${n.ring ? " · ring " + n.ring : ""}`,
    color: { background: inRing ? ringColor(n.ring) : riskColor(n.risk),
             border: inRing ? "#e6edf3" : "#161b22",
             highlight: { background: inRing ? ringColor(n.ring) : riskColor(n.risk), border: "#fff" } },
    borderWidth: inRing ? 2 : 1,
    font: { color: "#c9d1d9", size: 12 },
    opacity: inRing ? 1 : (flagged ? 0.95 : 0.45),
  };
}
function edgeStyle(e) {
  const col = e.ring ? ringColor(e.ring) : (e.suspicious ? "#ff5a5f" : "#30363d");
  return {
    id: e.id, from: e.source, to: e.target, arrows: "to",
    title: eur2(e.amount),
    width: e.ring ? 1.8 : 1,
    color: { color: col, opacity: e.ring ? 0.85 : (e.suspicious ? 0.6 : 0.18) },
  };
}

// Dim everything except `members`; null restores the normal view.
function highlightGraph(members) {
  if (!nodesDS) return;
  const set = members ? new Set(members) : null;
  activeMembers = set;
  nodesDS.update(viewNodes.map((n) => {
    const base = nodeStyle(n);
    if (!set) return base;
    const on = set.has(n.id);
    base.opacity = on ? 1 : 0.1;
    base.font = { color: on ? "#fff" : "rgba(201,209,217,0.15)", size: 12 };
    if (!on) base.color.background = "#222831";
    return base;
  }));
  edgesDS.update(viewEdges.map((e) => {
    const base = edgeStyle(e);
    if (!set) return base;
    const on = set.has(e.source) && set.has(e.target);
    base.color = { color: on ? base.color.color : "#20262f", opacity: on ? 0.95 : 0.05 };
    base.width = on ? 2.2 : 1;
    return base;
  }));
  if (set) {
    const present = [...set].filter((id) => nodesDS.get(id));
    if (present.length) network.fit({ nodes: present, animation: { duration: 500, easingFunction: "easeInOutQuad" } });
  }
}

// ── summary + eval ──────────────────────────────────────────────────────────
async function loadSummary() {
  const s = await fetch("/api/dataset/current").then((r) => r.json());
  $("summary").innerHTML =
    `<span class="chip"><b>${s.accounts}</b><span>accounts</span></span>` +
    `<span class="chip"><b>${s.transactions}</b><span>txns</span></span>` +
    `<span class="chip"><b>${s.rings_detected}</b><span>rings</span></span>` +
    `<span class="chip flagged"><b>${s.flagged_accounts}</b><span>flagged</span></span>`;
}

async function loadEval() {
  const e = await fetch("/api/eval").then((r) => r.json());
  const recall = e.ring_recall ?? 0;
  const cls = recall >= 0.9 ? "" : recall >= 0.6 ? "warn" : "bad";
  const fpCls = (e.false_positive_rings ?? 0) === 0 ? "good" : (e.false_positive_rings <= 3 ? "" : "bad");
  $("eval").innerHTML =
    `<div class="eval-hero">` +
      `<div class="big ${cls}">${pct(recall)}</div>` +
      `<div class="lead"><b>ring recall</b><small>${e.rings_matched ?? 0} of ${e.rings_true ?? 0} planted rings found</small></div>` +
    `</div>` +
    `<div class="eval-stats">` +
      `<div class="stat"><div class="v ${fpCls}">${e.false_positive_rings ?? "—"}</div><div class="k">false-pos rings</div></div>` +
      `<div class="stat"><div class="v">${(e.account?.precision ?? 0).toFixed(2)}</div><div class="k">acct precision</div></div>` +
      `<div class="stat"><div class="v">${(e.account?.recall ?? 0).toFixed(2)}</div><div class="k">acct recall</div></div>` +
    `</div>` +
    `<p class="hint" style="margin:10px 0 0">Detection is deterministic graph algorithms — the AI only writes the report.</p>`;
}

// ── rings list ──────────────────────────────────────────────────────────────
async function loadRings() {
  const rings = await fetch("/api/rings").then((r) => r.json());
  RING_COLOR = {};
  rings.forEach((r, i) => { RING_COLOR[r.ring_id] = RING_COLORS[i % RING_COLORS.length]; });
  $("rings-count").textContent = rings.length ? `${rings.length}` : "";
  const box = $("rings");
  if (!rings.length) { box.innerHTML = `<span class="empty">No rings detected yet.</span>`; return; }
  box.innerHTML = "";
  for (const r of rings) {
    const div = document.createElement("div");
    div.className = "ring";
    div.dataset.ring = r.ring_id;
    div.style.borderLeftColor = ringColor(r.ring_id);
    div.innerHTML =
      `<span class="score-badge">${(r.score * 100).toFixed(0)}</span>` +
      `<span class="rid">${esc(r.ring_id)}</span>` +
      `<div class="meta">${r.account_ids.length} accounts · ${r.tx_ids.length} txns · ${esc(r.patterns.join(", "))}</div>`;
    div.onclick = () => showRing(r.ring_id);
    box.appendChild(div);
  }
}

function markActiveRing(id) {
  document.querySelectorAll(".ring").forEach((el) => el.classList.toggle("active", el.dataset.ring === id));
}

// ── evidence rendering (human-readable per detector) ────────────────────────
function evidenceText(f) {
  const ev = f.evidence || {};
  const win = f.window ? ` between ${fmtDate(f.window.start)} and ${fmtDate(f.window.end)}` : "";
  switch (f.detector) {
    case "structuring":
      return `<b>${ev.count}</b> deposits totalling <b>${eur(ev.total)}</b>, each kept just under the ` +
        `<b>${eur(ev.threshold || REPORTING_THRESHOLD)}</b> reporting limit${win}.`;
    case "circular": {
      const cyc = ev.cycle || [];
      return `Funds loop back through <b>${ev.length || cyc.length}</b> accounts: ` +
        `<code>${esc(cyc.join(" → "))}${cyc.length ? " → " + esc(cyc[0]) : ""}</code>.`;
    }
    case "passthrough":
      return `Relay account: received <b>${eur(ev.in)}</b>, forwarded <b>${eur(ev.out)}</b> ` +
        `within <b>${ev.hours}h</b> to a different counterparty${win}.`;
    case "fan_in":
      return `Collector hub <code>${esc(ev.hub)}</code> took funds from <b>${ev.in_degree_window}</b> ` +
        `distinct senders within ${ev.window_hours}h.`;
    case "fan_out":
      return `Distributor hub <code>${esc(ev.hub)}</code> pushed funds to <b>${ev.out_degree_window}</b> ` +
        `distinct recipients within ${ev.window_hours}h.`;
    case "community":
      return `Dense sub-network of <b>${ev.size}</b> accounts (density ${ev.density}).`;
    default:
      return `<code>${esc(JSON.stringify(ev))}</code>`;
  }
}

// ── per-ring money-flow diagram (source → mule → destination) ───────────────
let flowNet = null;
function destroyFlow() { if (flowNet) { flowNet.destroy(); flowNet = null; } }

// Classify each ring account by how money moves through it within the ring.
function flowRole(inAmt, outAmt) {
  if (outAmt > 0 && inAmt <= outAmt * 0.15) return ["source", "#3fb950"];
  if (inAmt > 0 && outAmt <= inAmt * 0.15) return ["destination", "#ff5a5f"];
  return ["mule", "#e3b341"];
}

function renderRingFlow(r) {
  const el = $("ring-flow");
  if (!el) return;
  const members = new Set(r.account_ids);
  // aggregate transfers between ring accounts into one edge per (src,dst)
  const agg = {};
  for (const t of r.transactions || []) {
    if (!members.has(t.src) || !members.has(t.dst)) continue;
    const k = t.src + "|" + t.dst;
    (agg[k] ||= { src: t.src, dst: t.dst, amount: 0, count: 0 });
    agg[k].amount += t.amount; agg[k].count += 1;
  }
  let flows = Object.values(agg);
  destroyFlow();
  if (!flows.length) { el.innerHTML = `<div class="flow-empty">No internal transfers to chart for this ring.</div>`; return; }
  el.innerHTML = "";

  const inAmt = {}, outAmt = {};
  flows.forEach((f) => { outAmt[f.src] = (outAmt[f.src] || 0) + f.amount; inAmt[f.dst] = (inAmt[f.dst] || 0) + f.amount; });

  // keep it readable: chart the largest transfers only
  const CAP = 28;
  flows.sort((a, b) => b.amount - a.amount);
  const total = flows.length;
  flows = flows.slice(0, CAP);
  const used = new Set();
  flows.forEach((f) => { used.add(f.src); used.add(f.dst); });

  const maxThru = Math.max(...[...used].map((a) => (inAmt[a] || 0) + (outAmt[a] || 0)), 1);
  const nodes = [...used].map((a) => {
    const i = inAmt[a] || 0, o = outAmt[a] || 0;
    const [role, c] = flowRole(i, o);
    return { id: a, label: a.replace(/^ACC/, ""), shape: "dot", value: 6 + 26 * ((i + o) / maxThru),
      color: { background: c, border: "#0e1116", highlight: { background: c, border: "#fff" } },
      title: `${a} · ${role} · in ${eur(i)} · out ${eur(o)}`,
      font: { color: "#c9d1d9", size: 11 } };
  });
  const maxAmt = Math.max(...flows.map((f) => f.amount), 1);
  const edges = flows.map((f) => ({
    from: f.src, to: f.dst, arrows: "to", label: eur(f.amount),
    width: 1 + 5 * (f.amount / maxAmt),
    color: { color: "#6b7686", highlight: "#4da3ff" },
    font: { size: 9, color: "#9aa4af", strokeWidth: 3, strokeColor: "#0b0e13", align: "top" },
    smooth: { type: "cubicBezier", forceDirection: "horizontal", roundness: 0.45 },
  }));

  flowNet = new vis.Network(el, { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) }, {
    layout: { hierarchical: { enabled: true, direction: "LR", sortMethod: "directed",
                              nodeSpacing: 65, levelSeparation: 150, treeSpacing: 80 } },
    physics: false,
    interaction: { hover: true, dragNodes: true, dragView: true, zoomView: true },
    nodes: { scaling: { min: 8, max: 34 } },
  });
  flowNet.on("click", (p) => { if (p.nodes.length) showAccount(p.nodes[0]); });
  const note = $("flow-note");
  if (note) note.textContent = total > CAP ? `top ${CAP} of ${total} transfers` : `${total} transfers`;
}

// ── ring detail panel ───────────────────────────────────────────────────────
async function showRing(id) {
  const r = await fetch(`/api/rings/${id}`).then((x) => x.json());
  const col = ringColor(id);
  const d = $("detail");
  d.classList.remove("hidden");

  // group findings by detector, strongest first
  const byDet = {};
  for (const f of r.findings || []) (byDet[f.detector] ||= []).push(f);
  const evidenceHtml = Object.keys(byDet).map((det) => {
    const f = byDet[det].sort((a, b) => b.score - a.score)[0];
    return `<div class="ev"><div class="ev-head"><span class="ev-tag">${esc(det)}</span>` +
      `<span class="ev-score">score ${(f.score * 100).toFixed(0)} · ${byDet[det].length}×</span></div>` +
      `<div class="ev-body">${evidenceText(f)}</div></div>`;
  }).join("") || `<span class="empty">No detector evidence attached.</span>`;

  // transactions, newest activity first
  const txs = (r.transactions || []).slice().sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  const txRows = txs.map((t) => {
    const near = t.amount >= 0.7 * REPORTING_THRESHOLD && t.amount < REPORTING_THRESHOLD;
    return `<tr><td>${fmtDate(t.timestamp)}</td>` +
      `<td class="mono">${esc(t.src)} → ${esc(t.dst)}</td>` +
      `<td class="amt ${near ? "near" : ""}">${eur2(t.amount)}</td>` +
      `<td>${esc(t.channel)}</td></tr>`;
  }).join("");

  const keyAccts = (r.key_accounts || []).map((a) =>
    `<span class="pill acc" onclick="showAccount('${esc(a)}')">${esc(a)}</span>`).join("");

  d.innerHTML =
    `<div class="detail-head"><span class="ringdot" style="background:${col}"></span>` +
      `<h2>${esc(r.ring_id)}</h2><span class="score-badge">${(r.score * 100).toFixed(0)}</span></div>` +
    `<div>${r.patterns.map((p) => `<span class="pill">${esc(p)}</span>`).join("")}</div>` +
    `<p class="subtle">${r.account_ids.length} accounts · ${r.tx_ids.length} transactions · ` +
      `total ${eur(txs.reduce((s, t) => s + (t.amount || 0), 0))}</p>` +

    `<div class="section-label">Key accounts</div>${keyAccts || "<span class='empty'>—</span>"}` +

    `<div class="section-label">Why it's suspicious</div>` +
    `<div class="evidence">${evidenceHtml}</div>` +

    `<div class="section-label">Money flow <span id="flow-note" class="flow-note"></span></div>` +
    `<div class="flow-legend">` +
      `<span><i style="background:#3fb950"></i>source</span>` +
      `<span><i style="background:#e3b341"></i>mule / relay</span>` +
      `<span><i style="background:#ff5a5f"></i>destination</span>` +
      `<span class="flow-hint">edge width ∝ amount · click a node</span>` +
    `</div>` +
    `<div id="ring-flow" class="ring-flow"></div>` +

    `<div class="section-label">Transactions (${txs.length})</div>` +
    `<div class="tx-scroll"><table class="tx-table">` +
      `<thead><tr><th>When</th><th>Flow</th><th class="amt">Amount</th><th>Channel</th></tr></thead>` +
      `<tbody>${txRows || "<tr><td colspan='4' class='empty'>no transactions</td></tr>"}</tbody></table></div>` +

    `<div class="sar-actions"><button id="sarbtn" class="btn-primary">🧾 Generate SAR</button>` +
      `<span id="sarsource" class="sar-source"></span></div>` +
    `<pre class="sar" id="sarout">Click “Generate SAR” to draft the report an analyst would file.</pre>`;

  $("sarbtn").onclick = async () => {
    const btn = $("sarbtn");
    btn.disabled = true;
    $("sarout").textContent = "drafting SAR…";
    try {
      const out = await fetch(`/api/rings/${id}/sar`, { method: "POST" }).then((x) => x.json());
      $("sarout").textContent = out.narrative || JSON.stringify(out, null, 2);
      $("sarsource").textContent = out.source ? `source: ${out.source}` : "";
    } catch (e) {
      $("sarout").textContent = "SAR generation failed: " + e;
    } finally { btn.disabled = false; }
  };

  renderRingFlow(r);
  markActiveRing(id);
  activeRing = id;
  if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
  highlightGraph(r.account_ids);
  d.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ── account detail (node click) ─────────────────────────────────────────────
async function showAccount(id) {
  const a = await fetch(`/api/accounts/${id}`).then((x) => x.json());
  destroyFlow();
  const d = $("detail");
  d.classList.remove("hidden");
  const acc = a.account || {};
  const findings = (a.findings || []).slice().sort((x, y) => y.score - x.score);
  d.innerHTML =
    `<div class="detail-head"><span class="ringdot" style="background:${riskColor(a.risk)}"></span>` +
      `<h2>${esc(id)}</h2><span class="score-badge">${(a.risk * 100).toFixed(0)}</span></div>` +
    `<p class="subtle">${esc(acc.owner_name || "")} · ${esc(acc.account_type || "")} · ` +
      `${esc(acc.country || "")} · KYC ${esc(acc.kyc_risk || "")}</p>` +
    `<div class="section-label">Findings (${findings.length})</div>` +
    (findings.length
      ? `<div class="evidence">${findings.map((f) =>
          `<div class="ev"><div class="ev-head"><span class="ev-tag">${esc(f.detector)}</span>` +
          `<span class="ev-score">score ${(f.score * 100).toFixed(0)}</span></div>` +
          `<div class="ev-body">${evidenceText(f)}</div></div>`).join("")}</div>`
      : `<span class="empty">No detector flagged this account.</span>`) +
    `<div class="section-label">Recent transactions (${(a.transactions || []).length})</div>` +
    `<div class="tx-scroll"><table class="tx-table">` +
      `<thead><tr><th>When</th><th>Flow</th><th class="amt">Amount</th><th>Channel</th></tr></thead><tbody>` +
      (a.transactions || []).slice(0, 60).map((t) =>
        `<tr><td>${fmtDate(t.timestamp)}</td><td class="mono">${esc(t.src)} → ${esc(t.dst)}</td>` +
        `<td class="amt">${eur2(t.amount)}</td><td>${esc(t.channel)}</td></tr>`).join("") +
      `</tbody></table></div>`;
  markActiveRing(null);
  d.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
window.showAccount = showAccount; // referenced by inline onclick

// ── Ask MuleNet copilot ─────────────────────────────────────────────────────
function addMsg(cls, html) {
  const div = document.createElement("div");
  div.className = `msg ${cls}`;
  div.innerHTML = html;
  $("chat-log").appendChild(div);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return div;
}

$("chat-form").onsubmit = async (e) => {
  e.preventDefault();
  const input = $("chat-input");
  const q = input.value.trim();
  if (!q) return;
  input.value = "";
  addMsg("user", esc(q));
  const thinking = addMsg("bot thinking", "investigating…");
  try {
    const out = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    }).then((r) => r.json());
    thinking.remove();
    const trace = (out.tool_calls || []).map((t) =>
      `<span class="tool">🔧 ${esc(t.tool)}${t.input && Object.keys(t.input).length ? "(" + esc(Object.values(t.input).join(", ")) + ")" : ""}</span>`).join("");
    addMsg("bot",
      esc(out.answer || "(no answer)") +
      (trace ? `<div class="trace">${trace}</div>` : "") +
      (out.source && out.source !== "anthropic" ? `<div class="trace"><span class="tool">${esc(out.source)}</span></div>` : ""));
  } catch (err) {
    thinking.remove();
    addMsg("bot", "Copilot error: " + esc(err));
  }
};

// ── boot ────────────────────────────────────────────────────────────────────
async function refresh() {
  await loadRings();              // sets RING_COLOR first so the graph can use it
  await Promise.all([loadGraph(), loadSummary(), loadEval()]);
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && RING_COLOR[id]) showRing(id);   // deep-link: /#DET_001 opens that ring
}

$("fitbtn").onclick = () => { activeRing = null; markActiveRing(null); highlightGraph(null); if (network) network.fit({ animation: true }); };

const showallEl = $("showall");
if (showallEl) showallEl.onchange = (e) => { showAll = e.target.checked; renderGraph(); };

$("gen").onclick = async () => {
  const btn = $("gen");
  btn.disabled = true;
  $("summary").textContent = "generating…";
  $("detail").classList.add("hidden");
  try {
    await fetch("/api/dataset/generate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
    await refresh();
  } finally { btn.disabled = false; }
};

refresh();
