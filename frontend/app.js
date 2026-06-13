// MuleNet frontend — light analyst console, three-pane investigation UI. Owner: P4.
// Left: model eval + ranked ring queue · Center: static network graph · Right: inspector / copilot.

const $ = (id) => document.getElementById(id);
// keep first occurrence by id — guards the vis DataSet against any duplicate-id crash
const dedupeById = (arr) => { const seen = new Set(); return arr.filter((x) => !seen.has(x.id) && seen.add(x.id)); };
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

let network = null, nodesDS = null, edgesDS = null, lastGraph = null, stabilizeTimer = null;
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

// Watchlist screening (sanctions / PEP / adverse-media), keyed by account id.
const SCREEN_META = {
  sanctions: { icon: "⛔", cls: "scr-sanctions", short: "Sanctions" },
  pep: { icon: "🏛️", cls: "scr-pep", short: "PEP" },
  adverse_media: { icon: "📰", cls: "scr-adverse", short: "Adverse media" },
};
let SCREEN_BY_ID = {};
const screenMeta = (t) => SCREEN_META[t] || { icon: "⚠️", cls: "scr-other", short: "Watchlist" };
function screenBadges(list, full) {
  return (list || []).map((s) => {
    const m = screenMeta(s.type);
    return `<span class="scr-badge ${m.cls}" title="${esc(s.list)} — ${esc(s.detail || "")}">` +
      `${m.icon} ${esc(full ? s.label : m.short)}</span>`;
  }).join("");
}

// Temporal playback state.
let pb = { txs: [], members: null, k: 0, timer: null, playing: false };

// Accounts table + shared filtering.
const CHANNELS = ["wire", "sepa", "card", "crypto", "cash_deposit"];
let ALL_ACCOUNTS = [];
let curView = "graph", showNames = false;
let acctSort = { key: "risk", dir: -1 };
const FILTERS = { text: "", riskMin: 0, types: new Set(), kyc: new Set(), countries: new Set(),
  channels: new Set(), amtMin: null, amtMax: null, dateFrom: null, dateTo: null, watchlist: false,
  underReview: false };

const matchText = (id, owner) => {
  const t = FILTERS.text.trim().toLowerCase();
  return !t || id.toLowerCase().includes(t) || (owner || "").toLowerCase().includes(t);
};
function nodePasses(n) {
  if (FILTERS.watchlist && !n.screened) return false;
  if (FILTERS.riskMin && n.risk * 100 < FILTERS.riskMin) return false;
  if (FILTERS.types.size && !FILTERS.types.has(n.type)) return false;
  if (FILTERS.kyc.size && !FILTERS.kyc.has(n.kyc_risk)) return false;
  if (FILTERS.countries.size && !FILTERS.countries.has(n.country)) return false;
  return matchText(n.id, n.owner_name);
}
function edgePasses(e) {
  if (FILTERS.channels.size && !FILTERS.channels.has(e.channel)) return false;
  if (FILTERS.amtMin != null && e.amount < FILTERS.amtMin) return false;
  if (FILTERS.amtMax != null && e.amount > FILTERS.amtMax) return false;
  if (FILTERS.dateFrom && new Date(e.timestamp) < FILTERS.dateFrom) return false;
  if (FILTERS.dateTo && new Date(e.timestamp) > FILTERS.dateTo) return false;
  return true;
}
function acctPasses(a) {
  if (FILTERS.underReview && (a.status || "active") === "active") return false;
  if (FILTERS.watchlist && !(a.screening && a.screening.length)) return false;
  if (FILTERS.riskMin && a.risk * 100 < FILTERS.riskMin) return false;
  if (FILTERS.types.size && !FILTERS.types.has(a.account_type)) return false;
  if (FILTERS.kyc.size && !FILTERS.kyc.has(a.kyc_risk)) return false;
  if (FILTERS.countries.size && !FILTERS.countries.has(a.country)) return false;
  return matchText(a.account_id, a.owner_name);
}
function activeFilterCount() {
  let n = 0;
  if (FILTERS.text) n++;
  if (FILTERS.riskMin > 0) n++;
  if (FILTERS.types.size) n++;
  if (FILTERS.kyc.size) n++;
  if (FILTERS.countries.size) n++;
  if (FILTERS.channels.size) n++;
  if (FILTERS.amtMin != null || FILTERS.amtMax != null) n++;
  if (FILTERS.dateFrom || FILTERS.dateTo) n++;
  if (FILTERS.watchlist) n++;
  return n;
}

// ── graph (settles once, then freezes — no perpetual motion) ────────────────
async function loadGraph() {
  lastGraph = await fetch("/api/graph").then((r) => r.json());
  renderGraph();
}

function renderGraph() {
  const keep = new Set();
  viewNodes = dedupeById(lastGraph.nodes.filter((n) => showAll || inFocus(n)));
  viewNodes.forEach((n) => keep.add(n.id));
  viewEdges = dedupeById(lastGraph.edges.filter((e) =>
    keep.has(e.source) && keep.has(e.target) && (showAll || e.ring || e.suspicious)));

  if (network) network.destroy();   // avoid leaking the previous network on re-render
  nodesDS = new vis.DataSet(viewNodes.map(nodeStyle));
  edgesDS = new vis.DataSet(viewEdges.map(edgeStyle));
  showGraphLoading(true);   // hide the canvas while physics settles — no on-screen churn
  network = new vis.Network($("graph"), { nodes: nodesDS, edges: edgesDS }, {
    physics: { enabled: true, stabilization: { iterations: 220, fit: true },
               barnesHut: { gravitationalConstant: -14000, springLength: 150, springConstant: 0.04, avoidOverlap: 0.4 } },
    interaction: { hover: true, tooltipDelay: 100, dragNodes: true, dragView: true, zoomView: true },
    nodes: { shape: "dot", scaling: { min: 6, max: 42 }, borderWidth: 1.5 },
    edges: { smooth: { type: "continuous" }, width: 1 },
  });
  // Settle the layout behind the overlay, then freeze + reveal the finished graph,
  // so the user only ever sees the static result — never the nodes flying around.
  const settle = () => {
    if (!network) return;
    network.setOptions({ physics: false });   // freeze so nothing keeps drifting
    showGraphLoading(false);
    if (activeMembers) {                       // keep the focused ring framed after a re-render
      const present = [...activeMembers].filter((id) => nodesDS.get(id));
      if (present.length) network.fit({ nodes: present });
    }
  };
  network.once("stabilizationIterationsDone", () => { clearTimeout(stabilizeTimer); settle(); });
  clearTimeout(stabilizeTimer);
  stabilizeTimer = setTimeout(settle, 4000);   // safety net: reveal even if the event never fires
  network.on("click", (p) => {
    if (p.nodes.length) showAccount(p.nodes[0]);
    else if (activeRing || activeMembers) clearSelection();   // click empty canvas to deselect
  });
  network.on("doubleClick", (p) => {
    const n = lastGraph.nodes.find((x) => x.id === p.nodes[0]);
    if (n && n.ring) showRing(n.ring);
  });
  updateViewCount();
  if (activeMembers) highlightGraph([...activeMembers], false);   // style only; settle() does the fit
}

function showGraphLoading(on) {
  const g = $("graph"), o = $("graph-loading");
  if (g) g.classList.toggle("stabilizing", on);
  if (o) o.classList.toggle("hidden", !on);
}

function updateViewCount() {
  const visible = viewNodes.filter(nodePasses).length;
  const nc = $("nodecount"); if (nc) nc.textContent = `· ${visible} shown`;
  const vc = $("view-count");
  if (vc) vc.textContent = curView === "graph" ? `${visible} nodes` : `${ALL_ACCOUNTS.filter(acctPasses).length} accounts`;
  const lm = $("legend-mode");
  if (lm) lm.textContent = (showAll ? "Showing all accounts & traffic" : "Showing rings + flagged accounts") +
    (activeFilterCount() ? " · filtered" : ".");
}

// Labels off unless "Names" is on; tooltip always carries the human detail. The `hidden`
// flag reflects the active filters, so re-styling a node always re-applies the filter.
function nodeStyle(n) {
  const inRing = !!n.ring, flagged = n.risk >= 0.5;
  const value = inRing ? 22 + n.risk * 26 : flagged ? 12 + n.risk * 18 : 4 + n.risk * 6;
  return {
    id: n.id, label: showNames ? (n.owner_name || n.id) : "", value,
    hidden: !nodePasses(n),
    // vis renders node titles as plain text — keep it text (no HTML); CSS themes + wraps it.
    title: `${n.id}${n.owner_name ? " — " + n.owner_name : ""}\n` +
      `${n.type || ""}${n.country ? " · " + n.country : ""} · KYC ${n.kyc_risk || "?"}\n` +
      `risk ${pct(n.risk)}${n.ring ? " · ring " + n.ring : ""}`,
    // accounts on a watchlist get a bold red ring so they pop out of the graph
    color: { background: inRing ? ringColor(n.ring) : riskColor(n.risk),
             border: n.screened ? "#b91c1c" : (inRing ? "#1e293b" : "#94a3b8"),
             highlight: { background: inRing ? ringColor(n.ring) : riskColor(n.risk), border: n.screened ? "#b91c1c" : "#1e293b" } },
    borderWidth: n.screened ? 4 : (inRing ? 2 : 1),
    font: { color: "#0f172a", size: 12 },
    opacity: inRing ? 1 : (flagged ? 0.95 : 0.55),
  };
}
function edgeStyle(e) {
  const col = e.ring ? ringColor(e.ring) : (e.suspicious ? "#ef4444" : "#cbd5e1");
  return {
    id: e.id, from: e.source, to: e.target, arrows: "to",
    hidden: !edgePasses(e),
    title: `${eur2(e.amount)}${e.channel ? " · " + e.channel : ""}${e.timestamp ? " · " + fmtDate(e.timestamp) : ""}`,
    width: e.ring ? 1.6 : 1,
    color: { color: col, opacity: e.ring ? 0.8 : (e.suspicious ? 0.55 : 0.4) },
  };
}

function highlightGraph(members, doFit = true) {
  if (!nodesDS) return;
  const set = members ? new Set(members) : null;
  activeMembers = set;
  nodesDS.update(viewNodes.map((n) => {
    const base = nodeStyle(n);          // carries the filter `hidden`
    if (!set) return base;
    const on = set.has(n.id);
    base.opacity = on ? 1 : 0.12;
    if (!on) { base.color.background = "#e2e8f0"; base.color.border = "#e2e8f0"; }
    return base;
  }));
  edgesDS.update(viewEdges.map((e) => {
    const base = edgeStyle(e);          // resets filter `hidden`, clears any playback hide
    if (!set) return base;
    const on = set.has(e.source) && set.has(e.target);
    base.color = { color: on ? base.color.color : "#e2e8f0", opacity: on ? 0.9 : 0.15 };
    base.width = on ? 2.2 : 1;
    return base;
  }));
  if (set && doFit) {
    const present = [...set].filter((id) => nodesDS.get(id));
    if (present.length) network.fit({ nodes: present, animation: { duration: 450, easingFunction: "easeInOutQuad" } });
  }
}

// Re-apply node/edge styling (filters + names) without rebuilding the layout.
function applyGraphFilters() {
  if (!nodesDS) return;
  if (activeMembers) highlightGraph([...activeMembers], false);
  else { nodesDS.update(viewNodes.map(nodeStyle)); edgesDS.update(viewEdges.map(edgeStyle)); }
}

// ── top-bar KPIs + left-rail eval ───────────────────────────────────────────
function setKpis(s) {
  $("kpis").innerHTML =
    `<div class="kpi"><b>${s.accounts}</b><span>accounts</span></div>` +
    `<div class="kpi"><b>${(s.transactions || 0).toLocaleString()}</b><span>txns</span></div>` +
    `<div class="kpi"><b>${s.rings_detected}</b><span>rings</span></div>` +
    `<div class="kpi flag"><b>${s.flagged_accounts}</b><span>flagged</span></div>` +
    (s.screening_hits != null ? `<div class="kpi watch" title="Accounts matching sanctions / PEP / adverse-media lists"><b>${s.screening_hits}</b><span>⚠ watchlist</span></div>` : "");
}
async function loadSummary() { setKpis(await fetch("/api/dataset/current").then((r) => r.json())); }

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
  const ownerOf = {};
  (r.accounts || []).forEach((a) => { ownerOf[a.account_id] = a.owner_name; });
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
      title: `${a}${ownerOf[a] ? " — " + ownerOf[a] : ""}\n${role} · in ${eur(i)} · out ${eur(o)}`,
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
    return { id: e.id, hidden: !on || base.hidden, width: on ? 2.4 : 1, color: { color: base.color.color, opacity: 0.95 } };
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
  const res = await fetch(`/api/rings/${id}`);
  if (!res.ok) {   // stale id (e.g. an old deep-link after Generate) — don't crash
    toast(`<span class="t-ico">⚠️</span><div class="t-body">Ring <b>${esc(id)}</b> no longer exists.</div>`);
    clearSelection();
    return;
  }
  const r = await res.json();
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

  const ownerOf = {};
  (r.accounts || []).forEach((a) => { ownerOf[a.account_id] = a.owner_name; });

  const txs = (r.transactions || []).slice().sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  const txRows = txs.map((t) => {
    const near = t.amount >= 0.7 * REPORTING_THRESHOLD && t.amount < REPORTING_THRESHOLD;
    const flowTitle = `${ownerOf[t.src] || t.src} → ${ownerOf[t.dst] || t.dst}`;
    return `<tr><td>${fmtDate(t.timestamp)}</td><td class="mono" title="${esc(flowTitle)}">${esc(t.src)} → ${esc(t.dst)}</td>` +
      `<td class="amt ${near ? "near" : ""}">${eur2(t.amount)}</td><td>${esc(t.channel)}</td></tr>`;
  }).join("");

  const keyAccts = (r.key_accounts || []).map((a) =>
    `<span class="pill acc" onclick="showAccount('${esc(a)}')">${esc(a)}${ownerOf[a] ? " · " + esc(ownerOf[a]) : ""}</span>`).join("");

  // watchlist exposure across the ring's accounts
  const screenedMembers = (r.account_ids || []).filter((a) => SCREEN_BY_ID[a]);
  let scrBanner = "";
  if (screenedMembers.length) {
    const counts = {};
    screenedMembers.forEach((a) => SCREEN_BY_ID[a].forEach((s) => { counts[s.type] = (counts[s.type] || 0) + 1; }));
    const parts = Object.entries(counts).map(([t, n]) => `${n} ${screenMeta(t).short.toLowerCase()}`).join(" · ");
    scrBanner = `<div class="scr-alert">⚠️ <b>${screenedMembers.length} account${screenedMembers.length > 1 ? "s" : ""} on watchlists</b> — ${parts}</div>`;
  }

  d.innerHTML =
    `<button class="back-btn" onclick="clearSelection()">← Back to all rings</button>` +
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

    scrBanner +

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
      `<button id="reportbtn" class="btn-ghost">📄 Export report</button>` +
      `<button id="goamlbtn" class="btn-ghost" title="Download the structured STR filing (goAML XML)">⬇ goAML XML</button>` +
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
  $("reportbtn").onclick = () => exportReport(id);
  $("goamlbtn").onclick = () => downloadGoAML(id);

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
  INSPECTED_ACCT = id;
  const res = await fetch(`/api/accounts/${id}`);
  destroyFlow();
  hidePlayback();
  switchTab("inspector");
  if (!res.ok) {
    $("detail").innerHTML = `<div class="empty-state"><div class="ico">🚫</div><p>Account <b>${esc(id)}</b> not found.</p></div>`;
    markActiveRing(null);
    return;
  }
  const a = await res.json();
  const acc = a.account || {};
  const findings = (a.findings || []).slice().sort((x, y) => y.score - x.score);
  const backLabel = activeRing ? "← Back to " + activeRing : "← Back to all rings";
  $("detail").innerHTML =
    `<button class="back-btn" onclick="${activeRing ? `showRing('${esc(activeRing)}')` : "clearSelection()"}">${esc(backLabel)}</button>` +
    `<div class="detail-head"><span class="ringdot" style="background:${riskColor(a.risk)}"></span>` +
      `<h2>${esc(id)}</h2><span class="risk-chip ${riskTier(a.risk)}">risk ${(a.risk * 100).toFixed(0)}</span></div>` +
    `<p class="subtle">${esc(acc.owner_name || "")} · ${esc(acc.account_type || "")} · ` +
      `${esc(acc.country || "")} · KYC ${esc(acc.kyc_risk || "")}</p>` +
    `<div class="enf-block"><span class="fz-status st-${esc(acc.status || "active")}">${esc(acc.status || "active")}</span>` +
      `<span class="enf-actions">` +
        `<button class="fz-act" onclick="acctDecision('${esc(id)}','freeze')">Freeze</button>` +
        `<button class="fz-act block" onclick="acctDecision('${esc(id)}','block')">Block</button>` +
        `<button class="fz-act ban" onclick="acctDecision('${esc(id)}','ban')">Ban</button>` +
        `<button class="fz-act clear" onclick="acctDecision('${esc(id)}','clear')">Clear</button>` +
      `</span></div>` +
    ((a.screening && a.screening.length)
      ? `<div class="scr-panel">${a.screening.map((s) => { const m = screenMeta(s.type);
          return `<div class="scr-row"><span class="scr-badge ${m.cls}">${m.icon} ${esc(s.label)}</span>` +
            `<span class="scr-detail"><b>${esc(s.list)}</b> — ${esc(s.detail || "")}</span></div>`; }).join("")}</div>`
      : `<div class="scr-clear">✓ No sanctions / PEP / adverse-media matches</div>`) +
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

// Deselect: clear the ring highlight, reset the inspector, refit the whole graph.
function clearSelection() {
  activeRing = null;
  destroyFlow();
  hidePlayback();
  markActiveRing(null);
  highlightGraph(null);
  if (network) network.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } });
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  $("detail").innerHTML = `<div class="empty-state"><div class="ico">🔍</div>` +
    `<p>Select a ring from the queue to investigate the laundering pattern, money flow, and draft a SAR.</p></div>`;
}
window.clearSelection = clearSelection;

// ── one-click investigation report (printable / Save-as-PDF) ────────────────
async function exportReport(id) {
  const r = await fetch(`/api/rings/${id}`).then((x) => x.json());
  let sar = null;
  try { sar = await fetch(`/api/rings/${id}/sar`, { method: "POST" }).then((x) => x.json()); } catch (e) {}
  const w = window.open("", "_blank");
  if (!w) { toast(`<span class="t-ico">⚠️</span><div class="t-body">Allow pop-ups to export the report.</div>`); return; }
  w.document.write(buildReportHtml(r, sar));
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 500);
}

// download the structured goAML STR filing (server sets the filename)
function downloadGoAML(id) {
  const a = document.createElement("a");
  a.href = `/api/rings/${id}/goaml`;
  a.download = `STR_${id}.xml`;
  document.body.appendChild(a); a.click(); a.remove();
}

function buildReportHtml(r, sar) {
  const ownerOf = {}, kycOf = {}, riskOf = {};
  (r.accounts || []).forEach((a) => { ownerOf[a.account_id] = a.owner_name; kycOf[a.account_id] = a.kyc_risk; riskOf[a.account_id] = a.risk; });
  const txs = (r.transactions || []).slice().sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  const total = txs.reduce((s, t) => s + (t.amount || 0), 0);

  const sum = {};
  (r.findings || []).forEach((f) => { sum[f.detector] = (sum[f.detector] || 0) + f.score; });
  const sumTot = Object.values(sum).reduce((a, b) => a + b, 0) || 1;
  const breakdown = Object.entries(sum).sort((a, b) => b[1] - a[1])
    .map(([d, v]) => `${esc(d)} ${(v / sumTot * 100).toFixed(0)}%`).join(" · ");

  const byDet = {};
  (r.findings || []).forEach((f) => (byDet[f.detector] ||= []).push(f));
  const evidence = Object.keys(byDet).map((det) => {
    const f = byDet[det].sort((a, b) => b.score - a.score)[0];
    return `<li><b>${esc(det)}</b> — ${evidenceText(f)}</li>`;
  }).join("");

  const keyRows = (r.key_accounts || []).map((a) =>
    `<tr><td class="m">${esc(a)}</td><td>${esc(ownerOf[a] || "")}</td><td>${esc(kycOf[a] || "")}</td>` +
    `<td class="r">${Math.round((riskOf[a] || 0) * 100)}</td></tr>`).join("");
  const txRows = txs.map((t) =>
    `<tr><td>${fmtDate(t.timestamp)}</td><td class="m">${esc(t.src)} → ${esc(t.dst)}</td>` +
    `<td class="r">${eur2(t.amount)}</td><td>${esc(t.channel)}</td></tr>`).join("");

  const narrative = sar && sar.narrative ? esc(sar.narrative) : "(SAR narrative unavailable — AI offline.)";
  const now = new Date().toLocaleString("en-GB");

  return `<!doctype html><html><head><meta charset="utf-8"><title>MuleNet Report — ${esc(r.ring_id)}</title>
  <style>
    * { box-sizing: border-box; }
    body { font: 13px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; color: #0f172a; margin: 0; padding: 40px; }
    .doc { max-width: 820px; margin: 0 auto; }
    .head { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #4f46e5; padding-bottom: 14px; margin-bottom: 8px; }
    .brand { font-size: 22px; font-weight: 800; letter-spacing: -.02em; }
    .brand span { color: #4f46e5; }
    .doctype { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #64748b; margin-top: 4px; }
    .meta { text-align: right; font-size: 11px; color: #64748b; }
    h1 { font-size: 18px; margin: 18px 0 2px; }
    .chip { display: inline-block; background: #fef2f2; color: #dc2626; font-weight: 700; padding: 2px 10px; border-radius: 999px; font-size: 12px; }
    .lead { color: #334155; margin: 6px 0 0; }
    h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: #64748b; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin: 22px 0 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th { text-align: left; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0; padding: 5px 8px; }
    td { padding: 5px 8px; border-bottom: 1px solid #f1f5f9; }
    td.m { font-family: ui-monospace, Consolas, monospace; }
    td.r, th.r { text-align: right; }
    ul { margin: 6px 0; padding-left: 20px; } li { margin: 4px 0; }
    code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 11px; }
    pre { white-space: pre-wrap; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; font: 12px/1.5 ui-monospace, Consolas, monospace; }
    .foot { margin-top: 28px; border-top: 1px solid #e2e8f0; padding-top: 10px; font-size: 10.5px; color: #94a3b8; }
    @media print { body { padding: 0; } .noprint { display: none; } }
  </style></head><body><div class="doc">
    <div class="head">
      <div><div class="brand">🕸️ Mule<span>Net</span></div><div class="doctype">Suspicious Activity Investigation Report</div></div>
      <div class="meta">Report generated<br>${esc(now)}<br>Confidential</div>
    </div>
    <h1>${esc(r.ring_id)} <span class="chip">risk ${(r.score * 100).toFixed(0)}</span></h1>
    <p class="lead">${r.account_ids.length} accounts · ${txs.length} transactions · total <b>${eur(total)}</b><br>
      Patterns: ${(r.patterns || []).map(esc).join(", ")}</p>

    <h2>Risk breakdown</h2><p>${breakdown || "—"}</p>
    <h2>Key accounts</h2>
    <table><thead><tr><th>Account</th><th>Owner</th><th>KYC</th><th class="r">Risk</th></tr></thead><tbody>${keyRows || ""}</tbody></table>
    <h2>Why it is suspicious</h2><ul>${evidence || "<li>No detector evidence.</li>"}</ul>
    <h2>Transactions (${txs.length})</h2>
    <table><thead><tr><th>When</th><th>Flow</th><th class="r">Amount</th><th>Channel</th></tr></thead><tbody>${txRows || ""}</tbody></table>
    <h2>Suspicious Activity Report${sar && sar.source ? ` <span style="font-weight:400;text-transform:none;color:#94a3b8">(${esc(sar.source)})</span>` : ""}</h2>
    <pre>${narrative}</pre>
    <div class="foot">Generated by MuleNet · team KKKCP · iFX Hack 2026. Detection is deterministic graph analysis; the AI drafts the narrative only. This document is synthetic demo data.</div>
  </div></body></html>`;
}

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
  // rings (by id or pattern)
  const rings = ALL_RINGS
    .filter((r) => !q || (r.ring_id + " " + r.patterns.join(" ")).toLowerCase().includes(q))
    .sort((a, b) => b.score - a.score)
    .slice(0, 6)
    .map((r) => ({ type: "ring", id: r.ring_id, sub: `${r.account_ids.length} accounts · ${r.patterns.join(", ")}` }));
  // accounts (by id, OWNER NAME or country) over the full account list
  const accts = ALL_ACCOUNTS
    .filter((a) => !q || a.account_id.toLowerCase().includes(q)
      || (a.owner_name || "").toLowerCase().includes(q) || (a.country || "").toLowerCase().includes(q))
    .sort((a, b) => b.risk - a.risk)
    .slice(0, 8)
    .map((a) => ({ type: "account", id: a.account_id, owner: a.owner_name,
      sub: `${a.account_type || ""} · ${a.country || ""} · risk ${pct(a.risk)}` }));
  const list = [...rings, ...accts].slice(0, 14);
  $("search-results").innerHTML = list.length ? list.map((x, i) =>
    `<div class="sr-item ${i === 0 ? "sel" : ""}" data-type="${x.type}" data-id="${esc(x.id)}">` +
      `<span class="sr-type ${x.type}">${x.type}</span>` +
      `<span class="sr-id">${esc(x.id)}</span>` +
      (x.owner ? `<span class="sr-owner">${esc(x.owner)}</span>` : "") +
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
  else if (e.key === "Escape") {
    if (!$("search-modal").classList.contains("hidden")) closeSearch();
    else if (!$("filter-panel").classList.contains("hidden")) $("filter-panel").classList.add("hidden");
  }
});

// ── playback controls ───────────────────────────────────────────────────────
$("pb-play").onclick = () => { if (pb.playing) stopPlayback(); else startPlayback(); };
$("pb-range").oninput = (e) => { stopPlayback(); renderPlaybackFrame(+e.target.value); };
$("pb-close").onclick = () => { hidePlayback(); if (activeMembers) highlightGraph([...activeMembers]); };

// ── accounts table (center view #2) ─────────────────────────────────────────
async function loadAccounts() {
  ALL_ACCOUNTS = await fetch("/api/accounts").then((r) => r.json());
  SCREEN_BY_ID = {};
  ALL_ACCOUNTS.forEach((a) => { if (a.screening && a.screening.length) SCREEN_BY_ID[a.account_id] = a.screening; });
  await syncFreeze();        // build the review map + freeze count, sync the threshold control
  buildFilterOptions();
  renderAccountsTable();
}

// pull the freeze config + review queue (for the modal's "why frozen" reason) and update the toolbar
async function syncFreeze() {
  try {
    const [cfg, q] = await Promise.all([
      fetch("/api/freeze").then((r) => r.json()),
      fetch("/api/frozen").then((r) => r.json()),
    ]);
    FZ_QUEUE = {};
    q.forEach((a) => { FZ_QUEUE[a.account_id] = a; });
    const pct = Math.round((cfg.threshold ?? 0.9) * 100);
    if ($("fz-threshold")) { $("fz-threshold").value = pct; $("fz-val").textContent = pct; }
    if ($("fz-count")) $("fz-count").textContent = `${cfg.under_review || 0} under review`;
  } catch (e) {}
}

function renderAccountsTable() {
  if (!ALL_ACCOUNTS.length) return;
  const rows = ALL_ACCOUNTS.filter(acctPasses);
  const { key, dir } = acctSort;
  rows.sort((a, b) => {
    let x = a[key], y = b[key];
    if (key === "rings") { x = (a.rings || []).length; y = (b.rings || []).length; }
    if (key === "screening") { x = (a.screening || []).length; y = (b.screening || []).length; }
    if (typeof x === "string") { x = x.toLowerCase(); y = (y || "").toLowerCase(); }
    return x < y ? -dir : x > y ? dir : 0;
  });
  $("acct-count").textContent = `${rows.length} of ${ALL_ACCOUNTS.length} accounts` +
    (activeFilterCount() ? " (filtered)" : "");
  $("acct-body").innerHTML = rows.map((a) => {
    const tier = riskTier(a.risk);
    const rings = (a.rings || []).length;
    const status = a.status || "active";
    const id = esc(a.account_id);
    const act = (label, action, cls) =>
      `<button class="fz-act ${cls}" onclick="event.stopPropagation();acctDecision('${id}','${action}')">${label}</button>`;
    let actions;
    if (status === "active") actions = act("Freeze", "freeze", "");
    else if (status === "frozen")
      actions = `<button class="fz-act review" onclick="event.stopPropagation();openReview('${id}')">Review</button>` +
                act("Block", "block", "block") + act("Clear", "clear", "clear");
    else actions = act("Clear", "clear", "clear");   // blocked / banned → re-activate
    return `<tr onclick="showAccount('${id}')">` +
      `<td class="acct-mono">${id}</td>` +
      `<td>${esc(a.owner_name || "")}</td>` +
      `<td>${esc(a.account_type || "")}</td>` +
      `<td>${esc(a.country || "")}</td>` +
      `<td><span class="kyc-pill kyc-${esc(a.kyc_risk || "low")}">${esc(a.kyc_risk || "")}</span></td>` +
      `<td>${(a.screening && a.screening.length) ? screenBadges(a.screening, false) : "<span class='subtle'>clear</span>"}</td>` +
      `<td class="num">${a.n_findings || 0}</td>` +
      `<td>${rings ? `<span class="pill">${esc((a.rings || [])[0])}${rings > 1 ? " +" + (rings - 1) : ""}</span>` : "—"}</td>` +
      `<td class="num"><span class="risk-chip ${tier}">${(a.risk * 100).toFixed(0)}</span></td>` +
      `<td><span class="fz-status st-${esc(status)}">${esc(status)}</span></td>` +
      `<td class="acct-actions">${actions}</td></tr>`;
  }).join("") || `<tr><td colspan="11" class="subtle" style="padding:24px;text-align:center">No accounts match the filters.</td></tr>`;
  document.querySelectorAll("#acct-table th").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.sort === key);
    th.classList.toggle("asc", th.dataset.sort === key && dir === 1);
  });
}
document.querySelectorAll("#acct-table th").forEach((th) => th.onclick = () => {
  const k = th.dataset.sort;
  if (acctSort.key === k) acctSort.dir *= -1;
  else { acctSort.key = k; acctSort.dir = (k === "risk" || k === "n_findings" || k === "rings" || k === "screening") ? -1 : 1; }
  renderAccountsTable();
});

// ── filter panel ────────────────────────────────────────────────────────────
function renderChips(containerId, values, set) {
  const el = $(containerId);
  el.innerHTML = values.map((v) => `<button class="fchip ${set.has(v) ? "on" : ""}" data-v="${esc(v)}">${esc(v)}</button>`).join("");
  el.querySelectorAll(".fchip").forEach((b) => b.onclick = () => {
    const v = b.dataset.v;
    if (set.has(v)) set.delete(v); else set.add(v);
    b.classList.toggle("on");
    onFiltersChanged();
  });
}
function buildFilterOptions() {
  renderChips("f-type", ["personal", "business"], FILTERS.types);
  renderChips("f-kyc", ["low", "medium", "high"], FILTERS.kyc);
  renderChips("f-country", [...new Set(ALL_ACCOUNTS.map((a) => a.country).filter(Boolean))].sort(), FILTERS.countries);
  renderChips("f-channel", CHANNELS, FILTERS.channels);
}
function onFiltersChanged() {
  const n = activeFilterCount();
  const badge = $("filter-count");
  badge.textContent = n; badge.classList.toggle("hidden", n === 0);
  applyGraphFilters();
  updateViewCount();
  renderAccountsTable();
}
function resetFilters() {
  FILTERS.text = ""; FILTERS.riskMin = 0;
  FILTERS.types.clear(); FILTERS.kyc.clear(); FILTERS.countries.clear(); FILTERS.channels.clear();
  FILTERS.amtMin = FILTERS.amtMax = FILTERS.dateFrom = FILTERS.dateTo = null;
  FILTERS.watchlist = false; FILTERS.underReview = false;
  $("f-text").value = ""; $("f-risk").value = 0; $("f-risk-val").textContent = "0";
  $("f-amin").value = ""; $("f-amax").value = ""; $("f-dfrom").value = ""; $("f-dto").value = "";
  $("f-watchlist").checked = false;
  if ($("f-under-review")) $("f-under-review").checked = false;
  buildFilterOptions();
  onFiltersChanged();
}

$("filter-btn").onclick = () => $("filter-panel").classList.toggle("hidden");
$("filter-close").onclick = () => $("filter-panel").classList.add("hidden");
$("filter-reset").onclick = resetFilters;
$("f-text").oninput = (e) => { FILTERS.text = e.target.value; onFiltersChanged(); };
$("f-risk").oninput = (e) => { FILTERS.riskMin = +e.target.value; $("f-risk-val").textContent = e.target.value; onFiltersChanged(); };
$("f-amin").oninput = (e) => { FILTERS.amtMin = e.target.value === "" ? null : +e.target.value; onFiltersChanged(); };
$("f-amax").oninput = (e) => { FILTERS.amtMax = e.target.value === "" ? null : +e.target.value; onFiltersChanged(); };
$("f-dfrom").oninput = (e) => { FILTERS.dateFrom = e.target.value ? new Date(e.target.value) : null; onFiltersChanged(); };
$("f-dto").oninput = (e) => { FILTERS.dateTo = e.target.value ? new Date(e.target.value + "T23:59:59") : null; onFiltersChanged(); };
$("f-watchlist").onchange = (e) => { FILTERS.watchlist = e.target.checked; onFiltersChanged(); };

// ── center view toggle (Graph / Accounts) + name labels ─────────────────────
function setView(v) {
  curView = v;
  if (v !== "graph") pauseLive();   // leaving the graph just freezes the feed (resumable)
  document.querySelectorAll(".vt").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $("graph-view").classList.toggle("hidden", v !== "graph");
  $("accounts-view").classList.toggle("hidden", v !== "accounts");
  $("names-wrap").classList.toggle("hidden", v !== "graph");
  $("fp-tx").classList.toggle("hidden", v !== "graph");   // transaction filters only apply to the graph
  updateViewCount();
  if (v === "graph" && network) setTimeout(() => network.redraw(), 30);
}
document.querySelectorAll(".vt").forEach((b) => b.onclick = () => setView(b.dataset.view));
$("names").onchange = (e) => { showNames = e.target.checked; applyGraphFilters(); };

// ── dark mode ─────────────────────────────────────────────────────────────
// Theme is just a `data-theme` attribute on <html>; the no-flash bootstrap in
// index.html applies the saved choice before first paint, this only toggles it.
function applyTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  const btn = $("theme-btn");
  if (btn) { btn.textContent = dark ? "☀️" : "🌙"; btn.title = dark ? "Switch to light mode" : "Switch to dark mode"; }
}
function toggleTheme() {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const next = dark ? "light" : "dark";
  try { localStorage.setItem("mulenet_theme", next); } catch (e) {}
  applyTheme(next);
}
applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");
$("theme-btn").onclick = toggleTheme;

// ── live-feed notifications inbox (grouped by pattern, deduped by ring) ─────
// Live alerts used to be transient toasts only; we also persist each one here so
// the analyst can re-open the bell and review every ring the feed has flagged,
// grouped by laundering pattern. Repeat alerts for the same ring fold into a count.
let NOTIFS = {};
function loadNotifs() { try { NOTIFS = JSON.parse(localStorage.getItem("mulenet_notifs")) || {}; } catch (e) { NOTIFS = {}; } }
function saveNotifs() { try { localStorage.setItem("mulenet_notifs", JSON.stringify(NOTIFS)); } catch (e) {} }

const PAT_LABEL = { structuring: "Structuring", circular: "Circular flow", passthrough: "Pass-through",
  fan_in: "Fan-in", fan_out: "Fan-out", community: "Dense community", cycle: "Circular flow" };
const patLabel = (p) => PAT_LABEL[p] || (p ? p[0].toUpperCase() + p.slice(1).replace(/_/g, " ") : "Other");
function ago(ms) {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function recordNotif(ring) {
  const id = ring.ring_id;
  const patterns = ring.patterns || [];
  const n = ring.n_accounts ?? (ring.account_ids || []).length;
  const now = Date.now();
  const cur = NOTIFS[id];
  if (cur) { cur.count++; cur.last = now; cur.read = false; cur.patterns = patterns; cur.n_accounts = n; }
  else { NOTIFS[id] = { ring_id: id, patterns, n_accounts: n, count: 1, first: now, last: now, read: false }; }
  saveNotifs();
  updateNotifBadge();
  if (!$("notif-panel").classList.contains("hidden")) renderNotifs();
}
function unreadCount() { return Object.values(NOTIFS).filter((x) => !x.read).length; }
function updateNotifBadge() {
  const u = unreadCount(), badge = $("notif-badge");
  badge.textContent = u > 99 ? "99+" : u;
  badge.classList.toggle("hidden", u === 0);
}
function renderNotifs() {
  const list = $("notif-list"), entries = Object.values(NOTIFS);
  $("np-sub").textContent = entries.length ? `${entries.length} ring${entries.length > 1 ? "s" : ""}` : "";
  if (!entries.length) {
    list.innerHTML = `<div class="np-empty"><span class="ico">🔔</span>No live-feed alerts yet.<br/>Start the live feed to watch rings fire here.</div>`;
    return;
  }
  // group by primary pattern, newest ring first within each group
  const groups = {};
  for (const e of entries) { const k = (e.patterns && e.patterns[0]) || "other"; (groups[k] ||= []).push(e); }
  const order = Object.keys(groups).sort((a, b) =>
    Math.max(...groups[b].map((x) => x.last)) - Math.max(...groups[a].map((x) => x.last)));
  let html = "";
  for (const k of order) {
    const items = groups[k].sort((a, b) => b.last - a.last);
    html += `<div class="np-group-head"><span class="np-dot" style="--itemcolor:${detColor(k)}"></span>` +
      `${esc(patLabel(k))} <span class="gc">${items.length}</span></div>`;
    for (const e of items) {
      const col = detColor((e.patterns && e.patterns[0]) || "");
      html += `<div class="np-item ${e.read ? "" : "unread"}" data-ring="${esc(e.ring_id)}" style="--itemcolor:${col}">` +
        `<span class="np-dot"></span>` +
        `<div class="np-main"><div class="np-rid">${esc(e.ring_id)}</div>` +
        `<div class="np-meta">${e.n_accounts} accounts · ${esc((e.patterns || []).map(patLabel).join(", "))}</div></div>` +
        `<div class="np-when">${ago(e.last)}${e.count > 1 ? `<span class="np-count">×${e.count}</span>` : ""}</div></div>`;
    }
  }
  list.innerHTML = html;
  list.querySelectorAll(".np-item").forEach((el) => el.onclick = () => {
    const id = el.dataset.ring;
    if (NOTIFS[id]) { NOTIFS[id].read = true; saveNotifs(); updateNotifBadge(); }
    closeNotifs();
    showRing(id);
  });
}
function openNotifs() {
  $("notif-panel").classList.remove("hidden");
  Object.values(NOTIFS).forEach((x) => x.read = true);   // opening = read everything
  saveNotifs(); updateNotifBadge(); renderNotifs();
}
function closeNotifs() { $("notif-panel").classList.add("hidden"); }
function toggleNotifs() { $("notif-panel").classList.contains("hidden") ? openNotifs() : closeNotifs(); }
function clearNotifs() { NOTIFS = {}; saveNotifs(); updateNotifBadge(); renderNotifs(); }

$("notif-btn").onclick = (e) => { e.stopPropagation(); toggleNotifs(); };
$("notif-close").onclick = closeNotifs;
$("notif-clear").onclick = clearNotifs;
// click outside the panel closes it
document.addEventListener("click", (e) => {
  const panel = $("notif-panel");
  if (panel.classList.contains("hidden")) return;
  if (!panel.contains(e.target) && e.target !== $("notif-btn")) closeNotifs();
});
loadNotifs();
updateNotifBadge();

// ── live transaction feed (true real-time stream via P1's LiveFeed engine) ──
// Auto-starts on app load and polls /api/stream/next: new transactions appear as
// edges, the network grows, and freshly-detected rings fire 🚨 alerts.
// Pause = freeze (stop polling, keep the streamed data + the server-side stream
// alive); Resume = continue the SAME stream from exactly where it left off.
//   on:      currently polling
//   paused:  user stopped it; data is frozen on screen, stream is resumable
//   started: a server-side stream exists this session (resume continues it)
let live = { on: false, paused: false, started: false, timer: null, speed: 1 };

function toast(html, onClick) {
  const box = $("toasts");
  while (box.children.length >= 5) box.firstChild.remove();   // cap the stack
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = html;
  if (onClick) el.onclick = () => { onClick(); dismissToast(el); };
  box.appendChild(el);
  setTimeout(() => dismissToast(el), 5000);
}
function dismissToast(el) { if (!el.parentNode) return; el.classList.add("out"); setTimeout(() => el.remove(), 300); }

let livePrevented = 0;   // running count of transactions stopped because a party is frozen
function liveStats(s, clock) {
  $("live-stats").innerHTML =
    `<b>${(s.transactions || 0).toLocaleString()}</b> transactions · <b>${s.rings_detected}</b> rings · ` +
    `<b>${s.flagged_accounts}</b> flagged` +
    (livePrevented ? ` · <b class="blocked-stat">🛑 ${livePrevented.toLocaleString()}</b> blocked` : "") +
    `${clock ? ` · ${fmtDate(clock)}` : ""}`;
}
function fireRingAlert(ring) {
  const id = ring.ring_id;
  recordNotif(ring);   // persist to the grouped notifications inbox (survives the 5s toast)
  toast(`<span class="t-ico">🚨</span><div class="t-body"><b>Laundering ring detected</b>` +
    `<small>${esc(id)} · ${ring.n_accounts ?? (ring.account_ids || []).length} accounts · ${esc((ring.patterns || []).join(", "))}</small></div>`,
    () => showRing(id));
  const card = document.querySelector(`.ring[data-ring="${id}"]`);
  if (card) { card.classList.add("flash"); card.scrollIntoView({ block: "nearest" }); setTimeout(() => card.classList.remove("flash"), 1500); }
}

function clearLiveTimer() { if (live.timer) clearTimeout(live.timer); live.timer = null; }

// Reflect the current live state on both controls (toolbar button + banner).
function setLiveUI() {
  const bar = $("live-bar"), btn = $("live-btn"), stop = $("live-stop"), label = $("live-label");
  if (live.on) {                          // streaming
    btn.textContent = "⏸ Pause feed";
    stop.textContent = "⏸ Pause";
    bar.classList.remove("hidden", "paused");
    if (label) label.textContent = "LIVE";
  } else if (live.started) {              // paused — data frozen, stream resumable
    btn.textContent = "▶ Resume feed";
    stop.textContent = "▶ Resume";
    bar.classList.remove("hidden");
    bar.classList.add("paused");
    if (label) label.textContent = "PAUSED";
  } else {                                // not running at all
    btn.textContent = "▶ Live feed";
    bar.classList.add("hidden");
    bar.classList.remove("paused");
  }
}

// Begin a FRESH stream (boot, or restarting after Generate). Resets to initial().
async function startLive() {
  if (live.on) return;
  if (curView !== "graph") setView("graph");
  clearSelection();
  $("live-btn").disabled = true;
  let res;
  try { res = await fetch("/api/stream/start", { method: "POST" }).then((r) => r.json()); }
  catch (e) { toast(`<span class="t-ico">⚠️</span><div class="t-body">Could not start the live stream.</div>`); $("live-btn").disabled = false; return; }
  showAll = true; $("showall").checked = true;   // show the whole (small) live network
  livePrevented = 0;                              // fresh stream → reset the blocked-tx counter
  await refresh();
  live.on = true; live.paused = false; live.started = true; live.speed = 1;
  document.querySelectorAll(".spd").forEach((b) => b.classList.toggle("active", b.dataset.spd === "1"));
  $("live-btn").disabled = false;
  setLiveUI();
  liveStats(res.summary, null);
  scheduleLive();
}

// Freeze: stop polling but keep the streamed data on screen AND the server-side
// stream alive, so Resume can continue it. No /api/stream/stop, no refresh.
function pauseLive() {
  if (!live.on) return;
  live.on = false; live.paused = true;
  clearLiveTimer();
  setLiveUI();
}

// Continue the SAME stream from where it stopped — just resume polling.
function resumeLive() {
  if (live.on || !live.started) return;
  live.on = true; live.paused = false;
  setLiveUI();
  scheduleLive();
}

// Full stop (used by Generate): tear the live session down without restoring a
// fixture here — the caller decides what to load next.
function endLive() {
  live.on = false; live.paused = false; live.started = false;
  clearLiveTimer();
  setLiveUI();
}

function scheduleLive() {
  if (!live.on) return;
  const delay = Math.round((2200 + Math.random() * 900) / live.speed);   // ~1–3s at 1×
  live.timer = setTimeout(pollLive, delay);
}

// Pick a resting position for each freshly-minted live account NEXT TO a node it
// connects to, so new nodes slot in beside their neighbours and the frozen layout
// never has to re-run physics (no churn). New nodes that only link to other new
// nodes are placed once a neighbour has a spot; any orphan drops near an existing node.
function placeNewNodes(newNodes, edges) {
  const newIds = new Set(newNodes.map((n) => n.id));
  const need = new Set();
  for (const e of edges) {
    if (newIds.has(e.source) && !newIds.has(e.target)) need.add(e.target);
    if (newIds.has(e.target) && !newIds.has(e.source)) need.add(e.source);
  }
  const known = need.size ? network.getPositions([...need]) : {};
  const placed = {};
  const jitter = () => (Math.random() - 0.5) * 70;
  const toPlace = new Map(newNodes.map((n) => [n.id, n]));
  let progress = true;
  while (toPlace.size && progress) {
    progress = false;
    for (const id of [...toPlace.keys()]) {
      let anchor = null;
      for (const e of edges) {
        const other = e.source === id ? e.target : (e.target === id ? e.source : null);
        if (other && (known[other] || placed[other])) { anchor = known[other] || placed[other]; break; }
      }
      if (anchor) { placed[id] = { x: anchor.x + jitter(), y: anchor.y + jitter() }; toPlace.delete(id); progress = true; }
    }
  }
  if (toPlace.size) {   // no known neighbour yet — settle near an existing node
    const anyId = nodesDS.getIds().find((id) => !newIds.has(id));
    const c = anyId ? network.getPositions([anyId])[anyId] : { x: 0, y: 0 };
    for (const id of toPlace.keys()) placed[id] = { x: c.x + (Math.random() - 0.5) * 260, y: c.y + (Math.random() - 0.5) * 260 };
  }
  return placed;
}

async function pollLive() {
  if (!live.on) return;
  let b;
  try { b = await fetch("/api/stream/next").then((r) => r.json()); }
  catch (e) { scheduleLive(); return; }
  if (!live.on) return;
  if (b.detail) {   // server stream vanished (e.g. backend reloaded) — re-establish from scratch
    toast(`<span class="t-ico">⚠️</span><div class="t-body">Live stream reset — restarting.</div>`);
    live.on = false; live.started = false; startLive(); return;
  }
  if (b.prevented && b.prevented.length) {   // enforcement stopped a frozen account from transacting
    livePrevented += b.prevented.length;
    const p = b.prevented[0];
    toast(`<span class="t-ico">🛑</span><div class="t-body"><b>Blocked ${b.prevented.length} transaction${b.prevented.length === 1 ? "" : "s"}</b>` +
      `<small>frozen account · ${esc(p.src)} → ${esc(p.dst)} · €${(p.amount || 0).toLocaleString()}</small></div>`);
  }
  if (b.summary) { liveStats(b.summary, b.clock); setKpis(b.summary); }
  // 1) new accounts join as nodes first (placed beside a neighbour, layout stays frozen)
  //    so the rings/edges that reference them have somewhere to attach.
  const newNodes = (b.new_nodes || []).filter((n) => !nodesDS.get(n.id));
  if (newNodes.length) {
    const pos = placeNewNodes(newNodes, b.new_edges || []);
    nodesDS.add(newNodes.map((n) => {
      const s = nodeStyle(n);
      const p = pos[n.id];
      if (p) { s.x = p.x; s.y = p.y; }
      s.physics = false;                  // stay put — never tug the frozen layout
      return s;
    }));
    viewNodes.push(...newNodes);
    lastGraph.nodes.push(...newNodes);    // keep lastGraph in sync so a later re-render keeps the grown network
  }
  // 2) recolor the freshly-detected ring (its nodes now exist) + fire the alert
  if (b.ring) {
    await loadRings();                              // rebuild queue + RING_COLOR with the new ring
    const col = ringColor(b.ring.ring_id);
    nodesDS.update((b.ring.account_ids || []).filter((id) => nodesDS.get(id))
      .map((id) => ({ id, color: { background: col, border: "#1e293b" }, borderWidth: 2, opacity: 1 })));
    fireRingAlert(b.ring);
  }
  // 3) new transfers — endpoints now exist; add in final style (no pulse), skip dup ids
  const fresh = (b.new_edges || []).filter((e) =>
    nodesDS.get(e.source) && nodesDS.get(e.target) && !edgesDS.get(e.id));
  if (fresh.length) {
    edgesDS.add(fresh.map(edgeStyle));
    viewEdges.push(...fresh);
    lastGraph.edges.push(...fresh);       // keep lastGraph in sync for re-renders
  }
  scheduleLive();
}

// Toolbar + banner controls cycle: streaming → pause → resume → pause …
// First-ever click (no stream yet) starts fresh.
$("live-btn").onclick = () => { if (live.on) pauseLive(); else if (live.started) resumeLive(); else startLive(); };
$("live-stop").onclick = () => { if (live.on) pauseLive(); else resumeLive(); };
document.querySelectorAll(".spd").forEach((b) => b.onclick = () => {
  live.speed = +b.dataset.spd;
  document.querySelectorAll(".spd").forEach((x) => x.classList.toggle("active", x === b));
});

// ── boot ────────────────────────────────────────────────────────────────────
async function refresh() {
  await loadRings();
  await Promise.all([loadGraph(), loadSummary(), loadEval(), loadAccounts()]);
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && RING_COLOR[id]) showRing(id);
  const params = new URLSearchParams(location.search);
  if (params.get("view") === "accounts") setView("accounts");
  if (params.get("filters") === "1") $("filter-panel").classList.remove("hidden");
  const sq = params.get("q");
  if (sq) { openSearch(); $("search-input").value = sq; renderSearch(sq); }
}

$("fitbtn").onclick = () => clearSelection();
$("showall").onchange = (e) => { showAll = e.target.checked; renderGraph(); };

$("gen").onclick = async () => {
  const btn = $("gen");
  btn.disabled = true;
  btn.textContent = "Generating…";
  endLive();   // generating a fresh dataset ends the live session entirely
  showAll = false; $("showall").checked = false;
  try {
    await fetch("/api/dataset/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ seed: Math.floor(Math.random() * 1000000) }) });
    activeRing = null; activeMembers = null; destroyFlow(); hidePlayback();
    CASE = {}; try { localStorage.removeItem("mulenet_cases"); } catch (e) {}  // fresh dataset → fresh cases
    resetFilters();
    $("detail").innerHTML = `<div class="empty-state"><div class="ico">🔍</div><p>Select a ring from the queue to investigate.</p></div>`;
    await refresh();
  } finally { btn.disabled = false; btn.textContent = "↻ Generate"; }
};

// ── boot: load current state, then auto-start the live feed ─────────────────
// The app opens "live" — polling begins on load. Skip the auto-start when the URL
// deep-links into a specific fixture view (?view=, ?q=, ?filters=, #ring) or with
// ?live=0; ?live=1 forces live even alongside those params.
(async function boot() {
  await refresh();
  const p = new URLSearchParams(location.search);
  const forceLive = p.get("live") === "1";
  const deepLinked = p.get("live") === "0" || p.get("q") || p.get("view") || p.get("filters") || location.hash.slice(1);
  if (forceLive || !deepLinked) startLive();
})();

// ── enforcement: auto-freeze by risk threshold + per-account review (§6) ────
// Accounts ≥ the threshold are auto-frozen (default 90%). The Accounts table shows each
// account's status + actions; the toolbar slider re-applies the policy live.
var INSPECTED_ACCT = null;   // var (hoisted) so showAccount can set it safely
let FZ_QUEUE = {};           // account_id -> frozen item (incl. reason) for the review modal

async function applyThreshold(pct, notify) {
  const r = await fetch("/api/freeze", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ threshold: pct / 100 }) }).then((x) => x.json());
  await loadAccounts();   // re-pull statuses + freeze map, re-render the table
  if (notify) toast(`<span class="t-ico">🔒</span><div class="t-body"><b>Auto-froze ${r.count} account${r.count === 1 ? "" : "s"}</b>` +
    `<small>risk ≥ ${pct}% — review in the Accounts table</small></div>`);
}

async function acctDecision(id, action) {
  const res = await fetch(`/api/accounts/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }) }).then((x) => x.json());
  await loadAccounts();                                          // refresh the table + freeze map
  if (INSPECTED_ACCT === id) showAccount(id);                    // refresh the open inspector
  if (!$("review-modal").classList.contains("hidden") && $("rv-title").textContent === id) {
    const st = $("rv-status"); st.textContent = res.status; st.className = `fz-status st-${res.status}`;
  }
  return res;
}
window.acctDecision = acctDecision;

// review modal: account info + the reason it's under review + the decision actions
function openReview(id) {
  const a = FZ_QUEUE[id];
  if (!a) { showAccount(id); return; }   // not in the frozen set → just open the inspector
  const m = a.reason || {};
  $("rv-title").textContent = id;
  const st = $("rv-status"); st.textContent = a.status; st.className = `fz-status st-${a.status}`;
  $("rv-body").innerHTML =
    `<div class="rv-grid">` +
      `<div><span class="rv-k">Owner</span><span class="rv-v">${esc(a.owner_name || "—")}</span></div>` +
      `<div><span class="rv-k">Type</span><span class="rv-v">${esc(a.account_type || "—")}</span></div>` +
      `<div><span class="rv-k">KYC</span><span class="rv-v"><span class="kyc-pill kyc-${esc(a.kyc_risk || "low")}">${esc(a.kyc_risk || "—")}</span></span></div>` +
      `<div><span class="rv-k">Risk</span><span class="rv-v"><span class="risk-chip ${riskTier(a.risk)}">${(a.risk * 100).toFixed(0)}</span></span></div>` +
    `</div>` +
    `<div class="rv-reason"><div class="rv-reason-head">🔒 Why this account is under review</div>` +
      `<p>${esc(m.summary || "Frozen for manual review.")}</p>` +
      ((m.patterns && m.patterns.length)
        ? `<div class="rv-pats">${m.patterns.map((p) => `<span class="pill">${esc(p)}</span>`).join("")}</div>` : "") +
    `</div>` +
    ((m.findings && m.findings.length)
      ? `<div class="section-label">Detector triggers (${m.findings.length})</div>` +
        `<div class="evidence">${m.findings.map((f) =>
          `<div class="ev"><div class="ev-head"><span class="ev-tag">${esc(f.detector)}</span>` +
          `<span class="ev-score">score ${(f.score * 100).toFixed(0)}</span></div>` +
          `<div class="ev-body">${evidenceText(f)}</div></div>`).join("")}</div>`
      : `<p class="subtle">No detector findings — frozen on the aggregate risk score alone.</p>`) +
    `<div class="rv-actions">` +
      `<button class="fz-act block" onclick="acctDecision('${esc(id)}','block')">Block</button>` +
      `<button class="fz-act ban" onclick="acctDecision('${esc(id)}','ban')">Ban</button>` +
      `<button class="fz-act clear" onclick="acctDecision('${esc(id)}','clear')">Clear (unfreeze)</button>` +
      `<button class="btn-ghost" onclick="$('review-modal').classList.add('hidden');showAccount('${esc(id)}')">Open full inspector →</button>` +
    `</div>`;
  $("review-modal").classList.remove("hidden");
}
window.openReview = openReview;

// Accounts-toolbar auto-freeze slider + "under review only" filter
if ($("fz-threshold")) {
  $("fz-threshold").oninput = () => { $("fz-val").textContent = $("fz-threshold").value; };  // live label
  $("fz-threshold").onchange = (e) => applyThreshold(+e.target.value, true);                 // re-apply on release
}
if ($("f-under-review"))
  $("f-under-review").onchange = (e) => { FILTERS.underReview = e.target.checked; renderAccountsTable(); };
$("rv-close").onclick = () => $("review-modal").classList.add("hidden");
$("review-modal").addEventListener("click", (e) => { if (e.target.id === "review-modal") $("review-modal").classList.add("hidden"); });
