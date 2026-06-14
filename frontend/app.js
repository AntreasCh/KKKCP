// MuleNet frontend — minimal AML triage console. Owner: P4.
// Home = Accounts table + inspector. "Visual Review" opens a small account-scoped ego graph.

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
// Node fill = a risk heat scale: high → red, medium → amber, low → green.
function riskColor(r) {
  if (r >= 0.66) return "#dc2626";   // high risk
  if (r >= 0.33) return "#d97706";   // medium risk
  return "#22c55e";                  // low risk (green = safe)
}

let network = null, nodesDS = null, edgesDS = null, lastGraph = null, stabilizeTimer = null;
let focusAcct = null, focusMembers = null, focusHops = 1;   // account-focus (ego-network) mode
let activeMembers = null;
let viewNodes = [], viewEdges = [];

const inFocus = (n) => !!n.ring || n.risk >= 0.5;

// Accounts table + shared filtering.
let ALL_ACCOUNTS = [];
let curView = "accounts", showNames = false;
let acctSort = { key: "risk", dir: -1 };
const FILTERS = { underReview: false, q: "" };

function nodePasses(n) { return true; }
function edgePasses(e) { return true; }
function acctPasses(a) {
  if (focusMembers && !focusMembers.has(a.account_id)) return false;   // account-focus: only the ego set
  if (FILTERS.underReview && (a.status || "active") === "active") return false;
  if (FILTERS.q && !acctMatches(a, FILTERS.q)) return false;           // top search box
  return true;
}

// Dynamic free-text search: every query word must appear somewhere in the account's
// fields (name, id, type, country, status, KYC, risk %, ring ids). Space-separated
// terms are AND-ed, so "cyprus business" narrows to Cypriot business accounts.
function acctMatches(a, q) {
  const hay = [
    a.account_id, a.owner_name, a.account_type, a.country, a.status, a.kyc_risk,
    Math.round((a.risk || 0) * 100) + "%", (a.rings || []).join(" "),
  ].join(" ").toLowerCase();
  return q.split(/\s+/).every((term) => !term || hay.includes(term));
}

// Wired from the top search box (oninput). Filters the accounts list live; if the user
// is looking at the Visual Review graph, drop back to the accounts table so results show.
function onSearch(v) {
  FILTERS.q = (v || "").trim().toLowerCase();
  if (curView !== "accounts" && typeof setView === "function") setView("accounts");
  renderAccountsTable();
}

// ── account ego-graph renderer (Visual Review backend) ──────────────────────
// Renders the bounded ego set as a small, settled (frozen) graph. The graph canvas
// is only shown while focusAcct is set; renderGraph always shows the FULL ego set so
// legit counterparties stay visible for legit-vs-fraud judgement (§8 fix #2).
function renderGraph() {
  const keep = new Set();
  // When focused, render ALL nodes/edges from the bounded ego set (do NOT filter by inFocus/suspicious)
  // so legit counterparties still show. The non-focus branch keeps filtering by inFocus.
  viewNodes = dedupeById(focusAcct ? lastGraph.nodes : lastGraph.nodes.filter(inFocus));
  viewNodes.forEach((n) => keep.add(n.id));
  viewEdges = dedupeById(lastGraph.edges.filter((e) =>
    keep.has(e.source) && keep.has(e.target) && (focusAcct || e.ring || e.suspicious)));

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
    if (activeMembers) {                       // keep the focused set framed after a re-render
      const present = [...activeMembers].filter((id) => nodesDS.get(id));
      if (present.length) network.fit({ nodes: present });
    }
  };
  network.once("stabilizationIterationsDone", () => { clearTimeout(stabilizeTimer); settle(); });
  clearTimeout(stabilizeTimer);
  stabilizeTimer = setTimeout(settle, 4000);   // safety net: reveal even if the event never fires
  network.on("click", (p) => {
    if (p.nodes.length) showAccount(p.nodes[0]);
    else if (activeMembers) clearSelection();   // click empty canvas to deselect
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
  // when focused, always show the scale context: rendered nodes vs the full dataset size
  if (vc) {
    if (curView === "graph" && focusAcct) vc.textContent = `${visible} nodes · ${(GRAPH_TOTAL_TX || 0).toLocaleString()} total txns`;
    else vc.textContent = curView === "graph" ? `${visible} nodes` : `${ALL_ACCOUNTS.filter(acctPasses).length} accounts`;
  }
  const lm = $("legend-mode");
  if (lm) lm.textContent = focusAcct ? `Focused on ${focusAcct}'s network (${focusHops} hop${focusHops > 1 ? "s" : ""}).`
    : "Showing rings + flagged accounts.";
}
let GRAPH_TOTAL_TX = 0;   // full-dataset transaction count, for the "of N total" scale chip

// Labels off unless "Names" is on; tooltip always carries the human detail. The `hidden`
// flag reflects the active filters, so re-styling a node always re-applies the filter.
function nodeStyle(n) {
  const inRing = !!n.ring, flagged = n.risk >= 0.5;
  const isFocus = focusAcct && n.id === focusAcct;   // the account the ego-network is centred on
  const value = isFocus ? 48 : inRing ? 22 + n.risk * 26 : flagged ? 12 + n.risk * 18 : 4 + n.risk * 6;
  return {
    id: n.id, label: (showNames || isFocus) ? (n.owner_name || n.id) : "", value,
    hidden: !nodePasses(n),
    // vis renders node titles as plain text — keep it text (no HTML); CSS themes + wraps it.
    title: `${n.id}${n.owner_name ? " — " + n.owner_name : ""}\n` +
      `${n.type || ""}${n.country ? " · " + n.country : ""}\n` +
      `risk ${pct(n.risk)}${n.ring ? " · ring " + n.ring : ""}`,
    // fill always encodes RISK (red→amber→green); ring membership is shown with a violet ring border
    color: { background: riskColor(n.risk),
             border: isFocus ? "#4f46e5" : (inRing ? "#7c3aed" : "#94a3b8"),
             highlight: { background: riskColor(n.risk), border: isFocus ? "#4f46e5" : (inRing ? "#7c3aed" : "#1e293b") } },
    borderWidth: isFocus ? 5 : (inRing ? 3 : 1),
    font: { color: "#0f172a", size: isFocus ? 15 : 12 },
    opacity: isFocus || inRing ? 1 : (flagged ? 0.95 : 0.55),
  };
}
function edgeStyle(e) {
  // violet = part of a detected ring, red = suspicious transfer, grey = background
  const col = e.ring ? "#7c3aed" : (e.suspicious ? "#ef4444" : "#cbd5e1");
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
    const base = edgeStyle(e);          // resets filter `hidden`
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

// Re-apply node/edge styling (names) without rebuilding the layout.
function applyGraphFilters() {
  if (!nodesDS) return;
  if (activeMembers) highlightGraph([...activeMembers], false);
  else { nodesDS.update(viewNodes.map(nodeStyle)); edgesDS.update(viewEdges.map(edgeStyle)); }
}

// ── account focus: ego-network lens — the "Visual Review" feature ────────────
// Fetches a bounded slice — the account + its SUSPICIOUS counterparties + the transfers
// among them (suspicious_only) — so the render stays small/calm and shows the account
// plus the suspicious accounts associated with it. Renders into #graph.
async function focusOnAccount(id, hops = 1) {
  if (!id) return;
  if (curView !== "graph") setView("graph");
  showGraphLoading(true);
  let g;
  try { g = await fetch(`/api/graph/account/${encodeURIComponent(id)}?hops=${hops}&suspicious_only=true`).then((r) => r.json()); }
  catch (e) { showGraphLoading(false); toast(`<span class="t-ico">⚠️</span><div class="t-body">Couldn't load ${esc(id)}'s network.</div>`); return; }
  if (!g || g.detail) { showGraphLoading(false); toast(`<span class="t-ico">⚠️</span><div class="t-body">${esc((g && g.detail) || "Account not found")}</div>`); return; }
  focusAcct = id; focusHops = g.hops || hops;
  focusMembers = new Set(g.nodes.map((n) => n.id));
  GRAPH_TOTAL_TX = g.total_tx || 0;
  activeMembers = null;
  lastGraph = { nodes: g.nodes, edges: g.edges };
  renderGraph();                                   // overlay → settle → freeze (calm)
  setFocusUI(g);
  renderAccountsTable();                           // Accounts table now filtered to the ego set
}
window.focusOnAccount = focusOnAccount;

function setFocusUI(g) {
  const bar = $("focus-bar");
  if (bar) {
    bar.classList.toggle("hidden", !focusAcct);
    if (focusAcct && g) {
      const label = $("focus-label");
      if (label) label.innerHTML = `<b>${esc(focusAcct)}</b>${g.owner ? " · " + esc(g.owner) : ""} — ` +
        `${(g.tx_count || 0).toLocaleString()} transfer${g.tx_count === 1 ? "" : "s"} ` +
        `<span class="focus-scale">of ${(g.total_tx || 0).toLocaleString()} total</span>` +
        (g.truncated ? ` · <span class="focus-trunc">view capped</span>` : "");
      const hop = $("focus-hop");
      if (hop) hop.classList.toggle("hidden", focusHops >= 2);
    }
  }
  const note = $("focus-note");
  if (note) {
    note.classList.toggle("hidden", !focusAcct);
    if (focusAcct) note.innerHTML = `🔎 <b>${esc(focusAcct)}</b>'s network — <button class="link-btn" onclick="clearFocus()">back to accounts</button>`;
  }
  updateViewCount();
}

// §8 fix #1 — reset focus state and return to the Accounts view (no loadGraph / no showall).
function clearFocus() {
  focusAcct = null; focusMembers = null; focusHops = 1;
  activeMembers = null;
  setFocusUI(null);
  setView("accounts");
  renderAccountsTable();
}
window.clearFocus = clearFocus;

// reset focus state without reloading
function resetFocusState() { focusAcct = null; focusMembers = null; focusHops = 1; activeMembers = null; setFocusUI(null); }

// ── top-bar KPIs ─────────────────────────────────────────────────────────────
function setKpis(s) {
  $("kpis").innerHTML =
    `<div class="kpi"><b>${s.accounts}</b><span>accounts</span></div>` +
    `<div class="kpi"><b>${(s.transactions || 0).toLocaleString()}</b><span>txns</span></div>` +
    `<div class="kpi"><b>${s.rings_detected}</b><span>rings</span></div>` +
    `<div class="kpi flag"><b>${s.flagged_accounts}</b><span>flagged</span></div>`;
}
async function loadSummary() { setKpis(await fetch("/api/dataset/current").then((r) => r.json())); }

// ── ring colors (for Visual Review ring-coloring) ───────────────────────────
// Rings are no longer shown in a queue, but we still pull them to color ring members
// consistently in the ego graph + legend.
async function loadRingColors() {
  try {
    const rings = await fetch("/api/rings").then((r) => r.json());
    RING_COLOR = {};
    (rings || []).forEach((r, i) => { RING_COLOR[r.ring_id] = RING_COLORS[i % RING_COLORS.length]; });
  } catch (e) { RING_COLOR = {}; }
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

// ── inspector: account detail ───────────────────────────────────────────────
async function showAccount(id) {
  INSPECTED_ACCT = id;
  const res = await fetch(`/api/accounts/${id}`);
  switchTab("inspector");
  if (!res.ok) {
    $("detail").innerHTML = `<div class="empty-state"><div class="ico">🚫</div><p>Account <b>${esc(id)}</b> not found.</p></div>`;
    return;
  }
  const a = await res.json();
  const acc = a.account || {};
  const findings = (a.findings || []).slice().sort((x, y) => y.score - x.score);
  $("detail").innerHTML =
    `<button class="back-btn" onclick="clearSelection()">← Back to accounts</button>` +
    `<div class="detail-head"><span class="ringdot" style="background:${riskColor(a.risk)}"></span>` +
      `<h2>${esc(id)}</h2><span class="risk-chip ${riskTier(a.risk)}">risk ${(a.risk * 100).toFixed(0)}</span></div>` +
    `<p class="subtle">${esc(acc.owner_name || "")} · ${esc(acc.account_type || "")} · ` +
      `${esc(acc.country || "")}</p>` +
    `<div class="enf-block"><span class="fz-status st-${esc(acc.status || "active")}">${esc(acc.status || "active")}</span>` +
      `<span class="enf-actions">` +
        `<button class="fz-act" onclick="acctDecision('${esc(id)}','freeze')">Freeze</button>` +
        `<button class="fz-act block" onclick="acctDecision('${esc(id)}','block')">Block</button>` +
        `<button class="fz-act ban" onclick="acctDecision('${esc(id)}','ban')">Ban</button>` +
        `<button class="fz-act clear" onclick="acctDecision('${esc(id)}','clear')">Clear</button>` +
      `</span></div>` +
    `<div class="vr-block"><button class="ai-btn" onclick="focusOnAccount('${esc(id)}')">` +
      `🕸️ Visual Review</button></div>` +
    `<div class="ai-block"><button class="ai-btn" onclick="runAccountAnalysis('${esc(id)}')">` +
      `🔍 AI analysis</button><div id="ai-analysis" class="ai-analysis"></div></div>` +
    // risk signals — explains the score, incl. network association on accounts no detector flagged
    (() => {
      const sig = a.top_signals || [];
      if (!sig.length) return "";
      const label = (s) => s.detector === "network_association"
        ? "🔗 network association (transacts with high-risk accounts)"
        : esc(s.detector);
      return `<div class="section-label">Risk signals</div><div class="sig-list">` +
        sig.map((s) => `<div class="sig"><span class="sig-name">${label(s)}</span>` +
          `<span class="sig-score">${Math.round(s.score * 100)}</span></div>`).join("") + `</div>`;
    })() +
    `<div class="section-label">Findings (${findings.length})</div>` +
    (findings.length
      ? `<div class="evidence">${findings.map((f) =>
          `<div class="ev"><div class="ev-head"><span class="ev-tag">${esc(f.detector)}</span>` +
          `<span class="ev-score">score ${(f.score * 100).toFixed(0)}</span></div>` +
          `<div class="ev-body">${evidenceText(f)}</div></div>`).join("")}</div>`
      : ((a.top_signals || []).some((s) => s.detector === "network_association")
          ? `<span class="subtle">No detector flagged this account directly — its risk comes from <b>network association</b> (its money flows mostly to/from high-risk accounts).</span>`
          : `<span class="subtle">No detector flagged this account.</span>`)) +
    `<div class="section-label">Recent transactions (${(a.transactions || []).length})</div>` +
    `<div class="tx-scroll"><table class="tx-table">` +
      `<thead><tr><th>When</th><th>Flow</th><th class="amt">Amount</th><th>Channel</th></tr></thead><tbody>` +
      (a.transactions || []).slice(0, 60).map((t) =>
        `<tr><td>${fmtDate(t.timestamp)}</td><td class="mono">${esc(t.src)} → ${esc(t.dst)}</td>` +
        `<td class="amt">${eur2(t.amount)}</td><td>${esc(t.channel)}</td></tr>`).join("") +
      `</tbody></table></div>`;
  $("tab-inspector").scrollTop = 0;
}
window.showAccount = showAccount;

// Deselect: clear any graph highlight, reset the inspector to the empty state.
function clearSelection() {
  highlightGraph(null);
  if (network) network.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } });
  $("detail").innerHTML = `<div class="empty-state"><div class="ico">🔍</div>` +
    `<p>Select an account to inspect.</p></div>`;
}
window.clearSelection = clearSelection;

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

// ── inspector tab (Ask tab removed — just show the inspector) ────────────────
function switchTab(name) {
  const insp = $("tab-inspector");
  if (insp) insp.classList.remove("hidden");
}

// ── accounts table (home view) ──────────────────────────────────────────────
async function loadAccounts() {
  ALL_ACCOUNTS = await fetch("/api/accounts").then((r) => r.json());
  await syncFreeze();        // build the review map + freeze count
  renderAccountsTable();
}

// pull the freeze count + review queue (for the modal's "why frozen" reason) and update the toolbar
async function syncFreeze() {
  try {
    const [cfg, q] = await Promise.all([
      fetch("/api/freeze").then((r) => r.json()),
      fetch("/api/frozen").then((r) => r.json()),
    ]);
    FZ_QUEUE = {};
    q.forEach((a) => { FZ_QUEUE[a.account_id] = a; });
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
    if (typeof x === "string") { x = x.toLowerCase(); y = (y || "").toLowerCase(); }
    return x < y ? -dir : x > y ? dir : 0;
  });
  $("acct-count").textContent = `${rows.length} of ${ALL_ACCOUNTS.length} accounts`;
  $("acct-body").innerHTML = rows.map((a) => {
    const tier = riskTier(a.risk);
    const rings = (a.rings || []).length;
    const status = a.status || "active";
    const id = esc(a.account_id);
    const act = (label, action, cls) =>
      `<button class="fz-act ${cls}" onclick="event.stopPropagation();acctDecision('${id}','${action}')">${label}</button>`;
    const vrBtn = `<button class="fz-act txns" onclick="event.stopPropagation();focusOnAccount('${id}')" title="Open a small risk-colored graph of this account + its suspicious counterparties">Visual Review</button>`;
    let actions;
    if (status === "active") actions = vrBtn + act("Freeze", "freeze", "");
    else if (status === "frozen")
      actions = vrBtn + `<button class="fz-act review" onclick="event.stopPropagation();openReview('${id}')">Review</button>` +
                act("Block", "block", "block") + act("Clear", "clear", "clear");
    else actions = vrBtn + act("Clear", "clear", "clear");   // blocked / banned → re-activate
    return `<tr onclick="showAccount('${id}')">` +
      `<td class="acct-mono">${id}</td>` +
      `<td>${esc(a.owner_name || "")}</td>` +
      `<td>${esc(a.account_type || "")}</td>` +
      `<td>${esc(a.country || "")}</td>` +
      `<td class="num">${a.n_findings || 0}</td>` +
      `<td>${rings ? `<span class="pill">${esc((a.rings || [])[0])}${rings > 1 ? " +" + (rings - 1) : ""}</span>` : "—"}</td>` +
      `<td class="num"><span class="risk-chip ${tier}">${(a.risk * 100).toFixed(0)}</span></td>` +
      `<td><span class="fz-status st-${esc(status)}">${esc(status)}</span></td>` +
      `<td class="acct-actions">${actions}</td></tr>`;
  }).join("") || `<tr><td colspan="9" class="subtle" style="padding:24px;text-align:center">No accounts match the filters.</td></tr>`;
  document.querySelectorAll("#acct-table th").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.sort === key);
    th.classList.toggle("asc", th.dataset.sort === key && dir === 1);
  });
}
document.querySelectorAll("#acct-table th").forEach((th) => th.onclick = () => {
  const k = th.dataset.sort;
  if (!k) return;
  if (acctSort.key === k) acctSort.dir *= -1;
  else { acctSort.key = k; acctSort.dir = (k === "risk" || k === "n_findings" || k === "rings") ? -1 : 1; }
  renderAccountsTable();
});

// ── center view toggle (Accounts default; Graph only on Visual Review) ───────
function setView(v) {
  curView = v;
  const gv = $("graph-view"); if (gv) gv.classList.toggle("hidden", v !== "graph");
  const av = $("accounts-view"); if (av) av.classList.toggle("hidden", v !== "accounts");
  const nw = $("names-wrap"); if (nw) nw.classList.toggle("hidden", v !== "graph");
  const fb = $("fitbtn"); if (fb) fb.classList.toggle("hidden", v !== "graph");   // Fit only applies to the graph
  updateViewCount();
  if (v === "graph" && network) setTimeout(() => network.redraw(), 30);
}
if ($("names")) $("names").onchange = (e) => { showNames = e.target.checked; applyGraphFilters(); };

// ── toasts (kept) ───────────────────────────────────────────────────────────
function toast(html, onClick) {
  const box = $("toasts");
  if (!box) return;
  while (box.children.length >= 5) box.firstChild.remove();   // cap the stack
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = html;
  if (onClick) el.onclick = () => { onClick(); dismissToast(el); };
  box.appendChild(el);
  setTimeout(() => dismissToast(el), 5000);
}
function dismissToast(el) { if (!el.parentNode) return; el.classList.add("out"); setTimeout(() => el.remove(), 300); }

// account-focus banner controls
if ($("focus-hop")) $("focus-hop").onclick = () => { if (focusAcct) focusOnAccount(focusAcct, 2); };
if ($("focus-clear")) $("focus-clear").onclick = clearFocus;

// ── boot ────────────────────────────────────────────────────────────────────
async function refresh() {
  await loadRingColors();
  await Promise.all([loadSummary(), loadAccounts()]);
  setView("accounts");
}

$("gen").onclick = async () => {
  const btn = $("gen");
  btn.disabled = true;
  btn.textContent = "Generating…";
  resetFocusState();
  try {
    await fetch("/api/dataset/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ seed: Math.floor(Math.random() * 1000000) }) });
    $("detail").innerHTML = `<div class="empty-state"><div class="ico">🔍</div><p>Select an account to inspect.</p></div>`;
    await refresh();
  } finally { btn.disabled = false; btn.textContent = "↻ Generate"; }
};

(async function boot() {
  await refresh();
})();

// ── enforcement: auto-freeze by fixed risk threshold + per-account review ────
// Accounts at risk ≥ 0.90 are auto-frozen by the backend (fixed rule, no slider).
// The Accounts table shows each account's status + actions.
var INSPECTED_ACCT = null;   // var (hoisted) so showAccount can set it safely
let FZ_QUEUE = {};           // account_id -> frozen item (incl. reason) for the review modal

async function acctDecision(id, action) {
  const res = await fetch(`/api/accounts/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }) }).then((x) => x.json());
  await loadAccounts();                                          // refresh the table + freeze map
  if (INSPECTED_ACCT === id) showAccount(id);                    // refresh the open inspector
  if ($("review-modal") && !$("review-modal").classList.contains("hidden") && $("rv-title").textContent === id) {
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

// "Under review only" filter + review modal close wiring
if ($("f-under-review"))
  $("f-under-review").onchange = (e) => { FILTERS.underReview = e.target.checked; renderAccountsTable(); };
if ($("rv-close")) $("rv-close").onclick = () => $("review-modal").classList.add("hidden");
if ($("review-modal")) $("review-modal").addEventListener("click", (e) => { if (e.target.id === "review-modal") $("review-modal").classList.add("hidden"); });

// ── "Ask MuleNet" copilot — floating chat widget (P5) ───────────────────────────
// A tool-using agent: the backend gives the model tools to inspect rings/accounts/trace
// money, runs an agentic loop, and returns {answer, tool_calls, source}. We render the
// conversation as chat bubbles + a collapsible "investigation" trace for transparency.
const CHAT = { open: false, busy: false, history: [] };
const CHAT_KEY = "mulenet_chat";

function chatSave() { try { localStorage.setItem(CHAT_KEY, JSON.stringify(CHAT.history)); } catch (e) {} }
function chatLoad() { try { return JSON.parse(localStorage.getItem(CHAT_KEY) || "[]"); } catch (e) { return []; } }

function chatOpen() {
  CHAT.open = true;
  $("chat-panel").classList.remove("hidden");
  $("chat-fab").classList.add("hidden");
  if (!CHAT.history.length) chatRenderEmpty();   // only show the welcome when there's no conversation
  chatScroll();
  setTimeout(() => $("chat-input").focus(), 80);
}
function chatClose() {
  CHAT.open = false;
  $("chat-panel").classList.add("hidden");
  $("chat-fab").classList.remove("hidden");
}
function chatRenderEmpty() {
  $("chat-log").innerHTML =
    `<div class="chat-empty"><div class="ce-ico">🕸️</div>` +
    `<p><b>Ask MuleNet anything</b> about the detected network.<br/>` +
    `I investigate the rings, accounts and money trails with tools, then answer — try a suggestion below.</p></div>`;
}
function chatStatus(source) {
  const dot = $("chat-status-dot"), label = $("chat-status");
  dot.className = "ch-dot";
  if (source === "error" || source === "disabled") { dot.classList.add("err"); label.textContent = source === "disabled" ? "AI offline" : "error"; }
  else if (source) { dot.classList.add("ok"); label.textContent = "via " + source; }
  else { label.textContent = "AI analyst"; }
}

// very small, safe markdown-ish: **bold**, `code`, and line breaks (input already escaped)
function chatFormat(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/`([^`]+?)`/g, "<code>$1</code>");
}

function chatTrace(calls) {
  if (!calls || !calls.length) return "";
  const steps = calls.map((c) => {
    const args = c.input && Object.keys(c.input).length ? JSON.stringify(c.input) : "{}";
    const out = typeof c.output === "string" ? c.output : JSON.stringify(c.output, null, 2);
    return `<div class="tstep"><div class="tstep-h"><span class="ts-tool">${esc(c.tool)}</span>` +
      `<span class="ts-args">${esc(args)}</span></div><pre class="tstep-out">${esc(out)}</pre></div>`;
  }).join("");
  return `<details class="trace"><summary>🔍 Investigation · ${calls.length} step${calls.length === 1 ? "" : "s"}</summary>` +
    `<div class="trace-steps">${steps}</div></details>`;
}

// render one stored message to the log (no state change) — used by add + restore
function chatRenderMsg(m) {
  if ($("chat-log").querySelector(".chat-empty")) $("chat-log").innerHTML = "";
  const el = document.createElement("div");
  if (m.role === "user") {
    el.className = "msg user";
    el.innerHTML = `<div class="bubble">${esc(m.text)}</div>`;
  } else {
    el.className = "msg bot";
    el.innerHTML = `<div class="bubble">${chatFormat(m.answer)}</div>${chatTrace(m.calls)}` +
      (m.source && m.source !== "error" && m.source !== "disabled" ? `<div class="msg-meta">via ${esc(m.source)}</div>` : "");
  }
  $("chat-log").appendChild(el);
}

function chatAddUser(text) {
  const m = { role: "user", text };
  CHAT.history.push(m); chatSave();
  chatRenderMsg(m); chatScroll();
}

function chatAddBot(answer, calls, source) {
  const m = { role: "bot", answer, calls, source };
  CHAT.history.push(m); chatSave();
  chatRenderMsg(m); chatScroll();
}

// rebuild the log DOM from persisted history (on page load)
function chatRestore() {
  CHAT.history = chatLoad();
  if (!CHAT.history.length) return;
  $("chat-log").innerHTML = "";
  CHAT.history.forEach(chatRenderMsg);
  $("chat-suggest").classList.add("hidden");       // a conversation exists → hide the starter chips
  const last = [...CHAT.history].reverse().find((m) => m.role === "bot");
  if (last) chatStatus(last.source);
}

function chatTyping(on) {
  let t = $("chat-typing");
  if (on) {
    if (t) return;
    t = document.createElement("div");
    t.id = "chat-typing"; t.className = "msg bot";
    t.innerHTML = `<div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
    $("chat-log").appendChild(t);
    chatScroll();
  } else if (t) { t.remove(); }
}
function chatScroll() { const l = $("chat-log"); l.scrollTop = l.scrollHeight; }

async function chatSend(text) {
  text = (text || "").trim();
  if (!text || CHAT.busy) return;
  CHAT.busy = true;
  $("chat-input").value = "";
  $("chat-send").disabled = true;
  $("chat-suggest").classList.add("hidden");
  chatAddUser(text);
  chatTyping(true);
  let r;
  try {
    r = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text }),
    }).then((x) => x.json());
  } catch (e) {
    r = { answer: "⚠️ Couldn't reach the analyst service. Is the server running?", tool_calls: [], source: "error" };
  }
  chatTyping(false);
  chatAddBot(r.answer || "(no answer)", r.tool_calls, r.source);
  chatStatus(r.source);
  CHAT.busy = false;
  if (CHAT.open) $("chat-input").focus();
}

// wiring
if ($("chat-fab")) {
  $("chat-fab").onclick = chatOpen;
  $("chat-close").onclick = chatClose;
  $("chat-clear").onclick = () => { CHAT.history = []; chatSave(); chatRenderEmpty(); $("chat-suggest").classList.remove("hidden"); chatStatus(null); };
  $("chat-form").addEventListener("submit", (e) => { e.preventDefault(); chatSend($("chat-input").value); });
  $("chat-input").addEventListener("input", (e) => { $("chat-send").disabled = !e.target.value.trim() || CHAT.busy; });
  document.querySelectorAll(".cs-chip").forEach((b) => b.onclick = () => chatSend(b.dataset.q));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && CHAT.open) chatClose(); });
  chatRestore();   // re-hydrate any prior conversation so it survives close/reopen + reloads
}
