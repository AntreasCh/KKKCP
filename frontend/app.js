// MuleNet frontend — light analyst console, three-pane investigation UI. Owner: P4.
// Left: model eval + ranked ring queue · Center: static network graph · Right: inspector / copilot.

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

// Risk → chip class + label
function riskTier(r) { return r >= 0.66 ? "high" : r >= 0.33 ? "med" : "low"; }

// Ring palette tuned for a light canvas (saturated 600-ish hues).
const RING_COLORS = ["#4f46e5", "#0891b2", "#e11d48", "#d97706", "#7c3aed", "#059669",
  "#ea580c", "#0284c7", "#db2777", "#2563eb", "#65a30d", "#9333ea"];
let RING_COLOR = {};
function ringColor(id) { return RING_COLOR[id] || "#64748b"; }
function riskColor(r) {
  if (r >= 0.66) return "#dc2626";
  if (r >= 0.33) return "#d97706";
  return "#cbd5e1";
}

let network = null, nodesDS = null, edgesDS = null, lastGraph = null;
let activeRing = null, activeMembers = null;
let showAll = false;
let viewNodes = [], viewEdges = [];

const inFocus = (n) => !!n.ring || n.risk >= 0.5;

// Per-detector colors for the risk-breakdown bar.
const DET_COLORS = { structuring: "#dc2626", circular: "#7c3aed", passthrough: "#0891b2",
  fan_in: "#d97706", fan_out: "#ea580c", community: "#64748b" };
const detColor = (d) => DET_COLORS[d] || "#94a3b8";

// Case-management workflow (client-side, persisted to localStorage).
const CASE_STATUSES = {
  new: { label: "New", cls: "st-new" }, reviewing: { label: "Reviewing", cls: "st-rev" },
  escalated: { label: "Escalated", cls: "st-esc" }, cleared: { label: "Cleared", cls: "st-clr" },
  filed: { label: "SAR Filed", cls: "st-fil" },
};
let CASE = {};
try { CASE = JSON.parse(localStorage.getItem("mulenet_cases") || "{}"); } catch (e) { CASE = {}; }
const caseStatus = (id) => CASE[id] || "new";
let caseFilter = "all";

let ALL_RINGS = [];        // loaded rings (for search + case counts)
let ACCOUNT_INDEX = [];    // {id, risk, ring} for search

// Temporal playback state.
let pb = { txs: [], members: null, k: 0, timer: null, playing: false };

// ── graph (settles once, then freezes — no perpetual motion) ────────────────
async function loadGraph() {
  lastGraph = await fetch("/api/graph").then((r) => r.json());
  renderGraph();
}

function renderGraph() {
  const keep = new Set();
  viewNodes = lastGraph.nodes.filter((n) => showAll || inFocus(n));
  viewNodes.forEach((n) => keep.add(n.id));
  viewEdges = lastGraph.edges.filter((e) =>
    keep.has(e.source) && keep.has(e.target) && (showAll || e.ring || e.suspicious));

  nodesDS = new vis.DataSet(viewNodes.map(nodeStyle));
  edgesDS = new vis.DataSet(viewEdges.map(edgeStyle));
  network = new vis.Network($("graph"), { nodes: nodesDS, edges: edgesDS }, {
    physics: { enabled: true, stabilization: { iterations: 220, fit: true },
               barnesHut: { gravitationalConstant: -14000, springLength: 150, springConstant: 0.04, avoidOverlap: 0.4 } },
    interaction: { hover: true, tooltipDelay: 100, dragNodes: true, dragView: true, zoomView: true },
    nodes: { shape: "dot", scaling: { min: 6, max: 42 }, borderWidth: 1.5 },
    edges: { smooth: { type: "continuous" }, width: 1 },
  });
  // Freeze the layout the moment it settles, so nothing keeps drifting.
  network.once("stabilizationIterationsDone", () => network.setOptions({ physics: false }));
  network.on("click", (p) => { if (p.nodes.length) showAccount(p.nodes[0]); });
  network.on("doubleClick", (p) => {
    const n = lastGraph.nodes.find((x) => x.id === p.nodes[0]);
    if (n && n.ring) showRing(n.ring);
  });
  ACCOUNT_INDEX = lastGraph.nodes.map((n) => ({ id: n.id, risk: n.risk, ring: n.ring }));
  const nc = $("nodecount");
  if (nc) nc.textContent = `· ${viewNodes.length}${showAll ? "" : " key"} nodes`;
  if (activeMembers) highlightGraph([...activeMembers]);
}

// Labels hidden by default (tooltip carries the id); ring/flagged stand out.
function nodeStyle(n) {
  const inRing = !!n.ring, flagged = n.risk >= 0.5;
  const value = inRing ? 22 + n.risk * 26 : flagged ? 12 + n.risk * 18 : 4 + n.risk * 6;
  return {
    id: n.id, label: "", value,
    title: `${n.id} · risk ${pct(n.risk)}${n.ring ? " · ring " + n.ring : ""}`,
    color: { background: inRing ? ringColor(n.ring) : riskColor(n.risk),
             border: inRing ? "#1e293b" : "#94a3b8",
             highlight: { background: inRing ? ringColor(n.ring) : riskColor(n.risk), border: "#1e293b" } },
    borderWidth: inRing ? 2 : 1,
    font: { color: "#0f172a", size: 12 },
    opacity: inRing ? 1 : (flagged ? 0.95 : 0.55),
  };
}
function edgeStyle(e) {
  const col = e.ring ? ringColor(e.ring) : (e.suspicious ? "#ef4444" : "#cbd5e1");
  return {
    id: e.id, from: e.source, to: e.target, arrows: "to",
    title: eur2(e.amount),
    width: e.ring ? 1.6 : 1,
    color: { color: col, opacity: e.ring ? 0.8 : (e.suspicious ? 0.55 : 0.4) },
  };
}

function highlightGraph(members) {
  if (!nodesDS) return;
  const set = members ? new Set(members) : null;
  activeMembers = set;
  nodesDS.update(viewNodes.map((n) => {
    const base = nodeStyle(n);
    if (!set) return base;
    const on = set.has(n.id);
    base.opacity = on ? 1 : 0.12;
    if (!on) { base.color.background = "#e2e8f0"; base.color.border = "#e2e8f0"; }
    return base;
  }));
  edgesDS.update(viewEdges.map((e) => {
    const base = edgeStyle(e);
    base.hidden = false;                 // un-hide anything the playback scrubber hid
    if (!set) return base;
    const on = set.has(e.source) && set.has(e.target);
    base.color = { color: on ? base.color.color : "#e2e8f0", opacity: on ? 0.9 : 0.15 };
    base.width = on ? 2.2 : 1;
    return base;
  }));
  if (set) {
    const present = [...set].filter((id) => nodesDS.get(id));
    if (present.length) network.fit({ nodes: present, animation: { duration: 450, easingFunction: "easeInOutQuad" } });
  }
}

// ── top-bar KPIs + left-rail eval ───────────────────────────────────────────
async function loadSummary() {
  const s = await fetch("/api/dataset/current").then((r) => r.json());
  $("kpis").innerHTML =
    `<div class="kpi"><b>${s.accounts}</b><span>accounts</span></div>` +
    `<div class="kpi"><b>${s.transactions.toLocaleString()}</b><span>txns</span></div>` +
    `<div class="kpi"><b>${s.rings_detected}</b><span>rings</span></div>` +
    `<div class="kpi flag"><b>${s.flagged_accounts}</b><span>flagged</span></div>`;
}

async function loadEval() {
  const e = await fetch("/api/eval").then((r) => r.json());
  const recall = e.ring_recall ?? 0;
  const cls = recall >= 0.9 ? "" : recall >= 0.6 ? "warn" : "bad";
  const fp = e.false_positive_rings ?? 0;
  const fpCls = fp === 0 ? "good" : fp <= 3 ? "" : "bad";
  $("eval").innerHTML =
    `<div class="eval-top">` +
      `<div class="big ${cls}">${pct(recall)}</div>` +
      `<div class="lead">ring recall<small>${e.rings_matched ?? 0} of ${e.rings_true ?? 0} planted rings found</small></div>` +
    `</div>` +
    `<div class="eval-grid">` +
      `<div class="cell"><div class="v ${fpCls}">${fp}</div><div class="k">false-pos</div></div>` +
      `<div class="cell"><div class="v">${(e.account?.precision ?? 0).toFixed(2)}</div><div class="k">precision</div></div>` +
      `<div class="cell"><div class="v">${(e.account?.recall ?? 0).toFixed(2)}</div><div class="k">recall</div></div>` +
    `</div>` +
    `<p class="eval-note">Detection is deterministic graph algorithms — the AI only writes the report.</p>`;
}

// ── ring queue ──────────────────────────────────────────────────────────────
async function loadRings() {
  const rings = await fetch("/api/rings").then((r) => r.json());
  ALL_RINGS = rings;
  RING_COLOR = {};
  rings.forEach((r, i) => { RING_COLOR[r.ring_id] = RING_COLORS[i % RING_COLORS.length]; });
  $("rings-count").textContent = rings.length;
  const box = $("rings");
  if (!rings.length) { box.innerHTML = `<div class="empty-state"><p>No rings detected.</p></div>`; $("case-filter").innerHTML = ""; return; }
  box.innerHTML = "";
  for (const r of rings) {
    const tier = riskTier(r.score);
    const st = CASE_STATUSES[caseStatus(r.ring_id)];
    const div = document.createElement("div");
    div.className = "ring";
    div.dataset.ring = r.ring_id;
    div.style.setProperty("--ringcolor", ringColor(r.ring_id));
    div.innerHTML =
      `<span></span>` +
      `<div class="ring-main"><div class="rid">${esc(r.ring_id)}` +
        `<span class="status-chip ${st.cls}">${st.label}</span></div>` +
        `<div class="meta">${r.account_ids.length} accounts · ${r.tx_ids.length} txns · ${esc(r.patterns.join(", "))}</div></div>` +
      `<span class="ring-score risk-chip ${tier}">${(r.score * 100).toFixed(0)}</span>`;
    div.onclick = () => showRing(r.ring_id);
    box.appendChild(div);
  }
  renderCaseCounts();
  applyCaseFilter();
}

function markActiveRing(id) {
  document.querySelectorAll(".ring").forEach((el) => el.classList.toggle("active", el.dataset.ring === id));
}

// ── case workflow ───────────────────────────────────────────────────────────
function setCaseStatus(id, status) {
  CASE[id] = status;
  try { localStorage.setItem("mulenet_cases", JSON.stringify(CASE)); } catch (e) {}
  const m = CASE_STATUSES[status];
  const chip = document.querySelector(`.ring[data-ring="${id}"] .status-chip`);
  if (chip) { chip.className = `status-chip ${m.cls}`; chip.textContent = m.label; }
  const cur = $("case-current");
  if (cur && activeRing === id) { cur.className = `status-chip ${m.cls}`; cur.textContent = m.label; }
  document.querySelectorAll(".case-actions .ca-btn").forEach((b) => b.classList.toggle("active", b.dataset.status === status));
  renderCaseCounts();
  applyCaseFilter();
}

function renderCaseCounts() {
  const counts = { all: ALL_RINGS.length, new: 0, reviewing: 0, escalated: 0, cleared: 0, filed: 0 };
  ALL_RINGS.forEach((r) => { counts[caseStatus(r.ring_id)]++; });
  const order = ["all", "new", "reviewing", "escalated", "cleared", "filed"];
  $("case-filter").innerHTML = order.filter((k) => k === "all" || counts[k] > 0).map((k) => {
    const label = k === "all" ? "All" : CASE_STATUSES[k].label;
    return `<button class="cf-chip ${caseFilter === k ? "active" : ""}" data-cf="${k}">${label}<b>${counts[k]}</b></button>`;
  }).join("");
  $("case-filter").querySelectorAll(".cf-chip").forEach((b) =>
    b.onclick = () => { caseFilter = b.dataset.cf; renderCaseCounts(); applyCaseFilter(); });
}

function applyCaseFilter() {
  document.querySelectorAll(".ring").forEach((el) => {
    const show = caseFilter === "all" || caseStatus(el.dataset.ring) === caseFilter;
    el.classList.toggle("hidden", !show);
  });
}

// ── evidence text (human-readable per detector) ─────────────────────────────
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
function flowRole(inAmt, outAmt) {
  if (outAmt > 0 && inAmt <= outAmt * 0.15) return ["source", "#16a34a"];
  if (inAmt > 0 && outAmt <= inAmt * 0.15) return ["destination", "#dc2626"];
  return ["mule", "#d97706"];
}
function renderRingFlow(r) {
  const el = $("ring-flow");
  if (!el) return;
  const members = new Set(r.account_ids);
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
      color: { background: c, border: "#1e293b", highlight: { background: c, border: "#1e293b" } },
      title: `${a} · ${role} · in ${eur(i)} · out ${eur(o)}`,
      font: { color: "#0f172a", size: 11 } };
  });
  const maxAmt = Math.max(...flows.map((f) => f.amount), 1);
  const edges = flows.map((f) => ({
    from: f.src, to: f.dst, arrows: "to", label: eur(f.amount),
    width: 1 + 5 * (f.amount / maxAmt),
    color: { color: "#94a3b8", highlight: "#4f46e5" },
    font: { size: 9, color: "#475569", strokeWidth: 4, strokeColor: "#f8fafc", align: "top" },
    smooth: { type: "cubicBezier", forceDirection: "horizontal", roundness: 0.45 },
  }));

  flowNet = new vis.Network(el, { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) }, {
    layout: { hierarchical: { enabled: true, direction: "LR", sortMethod: "directed",
                              nodeSpacing: 65, levelSeparation: 150, treeSpacing: 80 } },
    physics: false,
    interaction: { hover: true, dragNodes: true, dragView: true, zoomView: true },
    nodes: { shape: "dot", scaling: { min: 8, max: 34 }, borderWidth: 1.5 },
  });
  flowNet.on("click", (p) => { if (p.nodes.length) showAccount(p.nodes[0]); });
  const note = $("flow-note");
  if (note) note.textContent = total > CAP ? `top ${CAP} of ${total} transfers` : `${total} transfers`;
}

// ── score-explainability bar (per-detector contribution to ring risk) ──────
function riskBreakdown(findings) {
  const sum = {};
  (findings || []).forEach((f) => { sum[f.detector] = (sum[f.detector] || 0) + f.score; });
  const parts = Object.entries(sum).sort((a, b) => b[1] - a[1]);
  const total = parts.reduce((a, [, v]) => a + v, 0);
  if (!total) return "";
  const bar = parts.map(([d, v]) =>
    `<div class="rb-seg" style="width:${(v / total * 100).toFixed(1)}%;background:${detColor(d)}" title="${esc(d)} ${(v / total * 100).toFixed(0)}%"></div>`).join("");
  const leg = parts.map(([d, v]) =>
    `<span class="rb-leg"><i style="background:${detColor(d)}"></i>${esc(d)} ${(v / total * 100).toFixed(0)}%</span>`).join("");
  return `<div class="section-label">Risk breakdown</div><div class="rb-bar">${bar}</div><div class="rb-legend">${leg}</div>`;
}

// ── temporal playback (scrub a ring's transactions over time) ───────────────
function stopPlayback() {
  if (pb.timer) clearInterval(pb.timer);
  pb.timer = null; pb.playing = false;
  const p = $("pb-play"); if (p) p.textContent = "▶";
}
function hidePlayback() { stopPlayback(); const el = $("playback"); if (el) el.classList.add("hidden"); }

function setupPlayback(r) {
  stopPlayback();
  pb.txs = (r.transactions || []).slice().sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  pb.members = new Set(r.account_ids);
  const el = $("playback");
  if (pb.txs.length < 2) { el.classList.add("hidden"); return; }
  el.classList.remove("hidden");
  const range = $("pb-range");
  range.min = 0; range.max = pb.txs.length; range.value = pb.txs.length;
  renderPlaybackFrame(pb.txs.length);   // start fully revealed
}

function renderPlaybackFrame(k) {
  pb.k = k;
  if (!pb.members || !nodesDS) return;
  const full = k >= pb.txs.length;
  const revealedTx = new Set(pb.txs.slice(0, k).map((t) => t.tx_id));
  const transacted = new Set();
  pb.txs.slice(0, k).forEach((t) => { transacted.add(t.src); transacted.add(t.dst); });
  edgesDS.update(viewEdges.filter((e) => pb.members.has(e.source) && pb.members.has(e.target)).map((e) => {
    const on = full || revealedTx.has(e.id);
    const base = edgeStyle(e);
    return { id: e.id, hidden: !on, width: on ? 2.4 : 1, color: { color: base.color.color, opacity: 0.95 } };
  }));
  nodesDS.update(viewNodes.filter((n) => pb.members.has(n.id)).map((n) => {
    const base = nodeStyle(n);
    base.opacity = (full || transacted.has(n.id)) ? 1 : 0.18;
    return base;
  }));
  const lbl = $("pb-label");
  if (lbl) lbl.textContent = k <= 0 ? "start" : full ? `full · ${pb.txs.length} txns`
    : `${k}/${pb.txs.length} · ${fmtDate(pb.txs[k - 1].timestamp)}`;
}

function playbackStep() {
  if (pb.k >= pb.txs.length) { stopPlayback(); return; }
  renderPlaybackFrame(pb.k + 1);
  $("pb-range").value = pb.k;
}
function startPlayback() {
  if (pb.txs.length < 2) return;
  if (pb.k >= pb.txs.length) { renderPlaybackFrame(0); $("pb-range").value = 0; }  // replay from start
  pb.playing = true; $("pb-play").textContent = "⏸";
  pb.timer = setInterval(playbackStep, Math.max(110, Math.min(380, 4500 / pb.txs.length)));
}

// ── inspector: ring detail ──────────────────────────────────────────────────
async function showRing(id) {
  const r = await fetch(`/api/rings/${id}`).then((x) => x.json());
  switchTab("inspector");
  const col = ringColor(id);
  const tier = riskTier(r.score);
  const d = $("detail");

  const byDet = {};
  for (const f of r.findings || []) (byDet[f.detector] ||= []).push(f);
  const evidenceHtml = Object.keys(byDet).map((det) => {
    const f = byDet[det].sort((a, b) => b.score - a.score)[0];
    return `<div class="ev"><div class="ev-head"><span class="ev-tag">${esc(det)}</span>` +
      `<span class="ev-score">score ${(f.score * 100).toFixed(0)} · ${byDet[det].length}×</span></div>` +
      `<div class="ev-body">${evidenceText(f)}</div></div>`;
  }).join("") || `<span class="subtle">No detector evidence attached.</span>`;

  const txs = (r.transactions || []).slice().sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  const txRows = txs.map((t) => {
    const near = t.amount >= 0.7 * REPORTING_THRESHOLD && t.amount < REPORTING_THRESHOLD;
    return `<tr><td>${fmtDate(t.timestamp)}</td><td class="mono">${esc(t.src)} → ${esc(t.dst)}</td>` +
      `<td class="amt ${near ? "near" : ""}">${eur2(t.amount)}</td><td>${esc(t.channel)}</td></tr>`;
  }).join("");

  const keyAccts = (r.key_accounts || []).map((a) =>
    `<span class="pill acc" onclick="showAccount('${esc(a)}')">${esc(a)}</span>`).join("");

  d.innerHTML =
    `<div class="detail-head"><span class="ringdot" style="background:${col}"></span>` +
      `<h2>${esc(r.ring_id)}</h2><span class="risk-chip ${tier}">risk ${(r.score * 100).toFixed(0)}</span></div>` +
    `<div class="case-bar"><span class="case-lbl">Case:</span>` +
      `<span id="case-current" class="status-chip ${CASE_STATUSES[caseStatus(id)].cls}">${CASE_STATUSES[caseStatus(id)].label}</span>` +
      `<div class="case-actions">` +
        `<button class="ca-btn" data-status="escalated">▲ Escalate</button>` +
        `<button class="ca-btn" data-status="cleared">✓ Clear</button>` +
        `<button class="ca-btn" data-status="filed">🧾 File SAR</button>` +
      `</div></div>` +
    `<div>${r.patterns.map((p) => `<span class="pill">${esc(p)}</span>`).join("")}</div>` +
    `<p class="subtle">${r.account_ids.length} accounts · ${r.tx_ids.length} transactions · ` +
      `total ${eur(txs.reduce((s, t) => s + (t.amount || 0), 0))}</p>` +

    riskBreakdown(r.findings) +

    `<div class="section-label">Key accounts</div>${keyAccts || "<span class='subtle'>—</span>"}` +

    `<div class="section-label">Why it's suspicious</div><div class="evidence">${evidenceHtml}</div>` +

    `<div class="section-label">Money flow <span id="flow-note" class="flow-note"></span></div>` +
    `<div class="flow-legend">` +
      `<span><i style="background:#16a34a"></i>source</span>` +
      `<span><i style="background:#d97706"></i>mule / relay</span>` +
      `<span><i style="background:#dc2626"></i>destination</span>` +
      `<span class="flow-hint">width ∝ amount · click a node</span>` +
    `</div><div id="ring-flow" class="ring-flow"></div>` +

    `<div class="section-label">Transactions (${txs.length})</div>` +
    `<div class="tx-scroll"><table class="tx-table">` +
      `<thead><tr><th>When</th><th>Flow</th><th class="amt">Amount</th><th>Channel</th></tr></thead>` +
      `<tbody>${txRows || "<tr><td colspan='4' class='subtle'>no transactions</td></tr>"}</tbody></table></div>` +

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

  // wire case-management actions; opening a "new" ring moves it to "reviewing"
  document.querySelectorAll(".case-actions .ca-btn").forEach((b) =>
    b.onclick = () => setCaseStatus(id, b.dataset.status));
  document.querySelectorAll(".case-actions .ca-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.status === caseStatus(id)));

  renderRingFlow(r);
  markActiveRing(id);
  activeRing = id;
  if (caseStatus(id) === "new") setCaseStatus(id, "reviewing");
  if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
  highlightGraph(r.account_ids);
  setupPlayback(r);
  $("tab-inspector").scrollTop = 0;
}

// ── inspector: account detail ───────────────────────────────────────────────
async function showAccount(id) {
  const a = await fetch(`/api/accounts/${id}`).then((x) => x.json());
  destroyFlow();
  hidePlayback();
  switchTab("inspector");
  const acc = a.account || {};
  const findings = (a.findings || []).slice().sort((x, y) => y.score - x.score);
  $("detail").innerHTML =
    `<div class="detail-head"><span class="ringdot" style="background:${riskColor(a.risk)}"></span>` +
      `<h2>${esc(id)}</h2><span class="risk-chip ${riskTier(a.risk)}">risk ${(a.risk * 100).toFixed(0)}</span></div>` +
    `<p class="subtle">${esc(acc.owner_name || "")} · ${esc(acc.account_type || "")} · ` +
      `${esc(acc.country || "")} · KYC ${esc(acc.kyc_risk || "")}</p>` +
    `<div class="ai-block"><button class="ai-btn" onclick="runAccountAnalysis('${esc(id)}')">` +
      `🔍 AI analysis</button><div id="ai-analysis" class="ai-analysis"></div></div>` +
    `<div class="section-label">Findings (${findings.length})</div>` +
    (findings.length
      ? `<div class="evidence">${findings.map((f) =>
          `<div class="ev"><div class="ev-head"><span class="ev-tag">${esc(f.detector)}</span>` +
          `<span class="ev-score">score ${(f.score * 100).toFixed(0)}</span></div>` +
          `<div class="ev-body">${evidenceText(f)}</div></div>`).join("")}</div>`
      : `<span class="subtle">No detector flagged this account.</span>`) +
    `<div class="section-label">Recent transactions (${(a.transactions || []).length})</div>` +
    `<div class="tx-scroll"><table class="tx-table">` +
      `<thead><tr><th>When</th><th>Flow</th><th class="amt">Amount</th><th>Channel</th></tr></thead><tbody>` +
      (a.transactions || []).slice(0, 60).map((t) =>
        `<tr><td>${fmtDate(t.timestamp)}</td><td class="mono">${esc(t.src)} → ${esc(t.dst)}</td>` +
        `<td class="amt">${eur2(t.amount)}</td><td>${esc(t.channel)}</td></tr>`).join("") +
      `</tbody></table></div>`;
  markActiveRing(null);
  $("tab-inspector").scrollTop = 0;
}
window.showAccount = showAccount;

// ── account AI analysis (P5): one-shot LLM read of the account + its connected accounts ──
async function runAccountAnalysis(id) {
  const box = $("ai-analysis");
  if (!box) return;
  box.classList.add("show");
  box.innerHTML = `<span class="subtle">🤖 analysing ${esc(id)} and its connected accounts…</span>`;
  try {
    const out = await fetch(`/api/accounts/${id}/analyze`, { method: "POST" }).then((r) => r.json());
    if (out.error) { box.innerHTML = `<span class="subtle">${esc(out.error)}</span>`; return; }
    const senders = (out.connected?.senders || []).length;
    const recips = (out.connected?.recipients || []).length;
    box.innerHTML =
      `<div class="ai-verdict">${esc(out.analysis || "(no analysis)")}</div>` +
      `<div class="ai-meta">${senders} senders · ${recips} recipients · via ${esc(out.source || "?")}</div>`;
  } catch (err) {
    box.innerHTML = `<span class="subtle">Analysis error: ${esc(err)}</span>`;
  }
}
window.runAccountAnalysis = runAccountAnalysis;

// ── tabs (Inspector / Ask MuleNet) ──────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $("tab-inspector").classList.toggle("hidden", name !== "inspector");
  $("tab-ask").classList.toggle("hidden", name !== "ask");
}
document.querySelectorAll(".tab").forEach((t) => { t.onclick = () => switchTab(t.dataset.tab); });

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

// ── global search / command palette (⌘K) ────────────────────────────────────
function openSearch() {
  $("search-modal").classList.remove("hidden");
  const i = $("search-input");
  i.value = ""; renderSearch(""); i.focus();
}
function closeSearch() { $("search-modal").classList.add("hidden"); }

function renderSearch(q) {
  q = q.trim().toLowerCase();
  const out = [];
  for (const r of ALL_RINGS) {
    const hay = (r.ring_id + " " + r.patterns.join(" ")).toLowerCase();
    if (!q || hay.includes(q)) out.push({ type: "ring", id: r.ring_id, sub: `${r.account_ids.length} accts · ${r.patterns.join(", ")}`, sort: -r.score });
  }
  let accts = ACCOUNT_INDEX.filter((a) => !q || a.id.toLowerCase().includes(q)).sort((a, b) => b.risk - a.risk);
  for (const a of accts.slice(0, 8)) out.push({ type: "account", id: a.id, sub: `risk ${pct(a.risk)}${a.ring ? " · ring " + a.ring : ""}` });
  if (/^acc/i.test(q) && !ACCOUNT_INDEX.some((a) => a.id.toLowerCase() === q))
    out.push({ type: "account", id: q.toUpperCase(), sub: "open account" });
  const rings = out.filter((x) => x.type === "ring").sort((a, b) => (a.sort || 0) - (b.sort || 0));
  const list = [...rings, ...out.filter((x) => x.type === "account")].slice(0, 12);
  $("search-results").innerHTML = list.length ? list.map((x, i) =>
    `<div class="sr-item ${i === 0 ? "sel" : ""}" data-type="${x.type}" data-id="${esc(x.id)}">` +
      `<span class="sr-type ${x.type}">${x.type}</span><span class="sr-id">${esc(x.id)}</span>` +
      `<span class="sr-sub">${esc(x.sub || "")}</span></div>`).join("")
    : `<div class="sr-empty">No matches for “${esc(q)}”</div>`;
  $("search-results").querySelectorAll(".sr-item").forEach((el) => el.onclick = () => pickSearch(el));
}
function pickSearch(el) {
  closeSearch();
  if (el.dataset.type === "ring") showRing(el.dataset.id); else showAccount(el.dataset.id);
}

$("search-btn").onclick = openSearch;
$("search-modal").onclick = (e) => { if (e.target.id === "search-modal") closeSearch(); };
$("search-input").oninput = (e) => renderSearch(e.target.value);
$("search-input").onkeydown = (e) => {
  const items = [...$("search-results").querySelectorAll(".sr-item")];
  let i = items.findIndex((x) => x.classList.contains("sel"));
  if (e.key === "ArrowDown") { e.preventDefault(); if (items.length) { if (i >= 0) items[i].classList.remove("sel"); items[Math.min(items.length - 1, i + 1)].classList.add("sel"); } }
  else if (e.key === "ArrowUp") { e.preventDefault(); if (items.length) { if (i >= 0) items[i].classList.remove("sel"); items[Math.max(0, i - 1)].classList.add("sel"); } }
  else if (e.key === "Enter") { e.preventDefault(); const sel = items.find((x) => x.classList.contains("sel")) || items[0]; if (sel) pickSearch(sel); }
  else if (e.key === "Escape") closeSearch();
};
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openSearch(); }
  else if (e.key === "Escape" && !$("search-modal").classList.contains("hidden")) closeSearch();
});

// ── playback controls ───────────────────────────────────────────────────────
$("pb-play").onclick = () => { if (pb.playing) stopPlayback(); else startPlayback(); };
$("pb-range").oninput = (e) => { stopPlayback(); renderPlaybackFrame(+e.target.value); };
$("pb-close").onclick = () => { hidePlayback(); if (activeMembers) highlightGraph([...activeMembers]); };

// ── boot ────────────────────────────────────────────────────────────────────
async function refresh() {
  await loadRings();
  await Promise.all([loadGraph(), loadSummary(), loadEval()]);
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && RING_COLOR[id]) showRing(id);
}

$("fitbtn").onclick = () => { activeRing = null; markActiveRing(null); hidePlayback(); highlightGraph(null); if (network) network.fit({ animation: true }); };
$("showall").onchange = (e) => { showAll = e.target.checked; renderGraph(); };

$("gen").onclick = async () => {
  const btn = $("gen");
  btn.disabled = true;
  btn.textContent = "Generating…";
  try {
    await fetch("/api/dataset/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    activeRing = null; activeMembers = null; destroyFlow(); hidePlayback();
    CASE = {}; try { localStorage.removeItem("mulenet_cases"); } catch (e) {}  // fresh dataset → fresh cases
    $("detail").innerHTML = `<div class="empty-state"><div class="ico">🔍</div><p>Select a ring from the queue to investigate.</p></div>`;
    await refresh();
  } finally { btn.disabled = false; btn.textContent = "↻ Generate"; }
};

refresh();
