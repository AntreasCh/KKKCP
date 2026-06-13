"""MuleNet synthetic data generator — REQUIREMENTS.md §13 (Owner: P1).

**Stdlib only** so it runs with zero installs and produces the committed fixture.
Emits realistic background traffic + planted laundering rings, with ground-truth labels.

    python -m backend.data.generator --accounts 800 --legit-tx 4000 --rings 15 --seed 42

Design goals (Phase 1):
- **2–3 instances per laundering pattern** so detectors are tested on variety, not one example.
- **Realistic legit noise** — salaries, merchant card spend, recurring bills, P2P — including
  *legit high-degree hubs* (employers, merchants) that detectors must learn NOT to flag.
- **Hard-negative decoys** — legit structures that *superficially* look like laundering (payday
  payroll bursts, merchant flash-sale fan-in, sub-threshold B2B invoices, inter-company
  settlement loops). They are NOT in the labels, so any detector that flags one is a true
  false-positive. They carry a fair legit signature (business + low-KYC + aged account) so a
  robust detector can still separate them — this is what makes precision genuinely *earned*.
- **AMLSim-aligned typologies.** We mirror the IBM AMLSim benchmark's laundering shapes
  (fan-in, fan-out, cycle, stack/layering, structuring/smurfing) for credibility, while keeping
  our frozen `schemas.py` contract. `evidence`-style typology names live in the docstrings below.

Labels distinguish two things on purpose:
- `rings[].account_ids` = **every** account touched by the ring (used for ring-recall overlap).
- `mule_accounts`       = only the **central / relay** accounts that should score high risk
  (hubs, cycle members, layering relays) — so account-precision isn't punished for one-shot smurfs.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

THRESHOLD = 10_000.0  # EUR reporting threshold; structuring sits just under it

FIRST = ["Maria", "Andreas", "Elena", "Nikos", "Sofia", "Petros", "Anna", "Giorgos",
         "Christina", "Marios", "Despina", "Kostas", "Ioanna", "Panayiotis", "Eleni",
         "Dimitris", "Katerina", "Stelios", "Chloe", "Vasilis", "Savvas", "Marina",
         "Antonis", "Theodora", "Michalis", "Natasa", "Pavlos", "Lefteris", "Zoe"]
LAST = ["Kattimeris", "Georgiou", "Christodoulou", "Ioannou", "Konstantinou", "Petrou",
        "Nikolaou", "Charalambous", "Andreou", "Demetriou", "Pavlou", "Antoniou", "Hadji",
        "Savva", "Theodorou", "Michael", "Stavrou", "Loizou", "Economou"]
# Business names for the legit hubs (employers / merchants / utilities).
BIZ = ["Aphrodite Foods Ltd", "Limassol Retail Co", "Nicosia Tech AE", "Paphos Logistics",
       "Cyprus Telecom", "EAC Power", "WaterBoard CY", "MedNet Clinics", "Olympus Cafe",
       "Larnaca Imports", "Aegean Construction", "Helios Energy", "BlueWave Trading"]
COUNTRIES = ["CY", "CY", "CY", "CY", "GR", "GR", "GB", "DE", "BG"]
# Higher-risk jurisdictions used more often by laundering accounts than by background ones.
HIGH_RISK_CC = ["RU", "AE", "CY", "BG"]
CHANNELS = ["sepa", "wire", "card", "crypto", "cash_deposit"]
BASE = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)

# The five typologies we plant; round-robined across the requested ring count.
PATTERNS = ["structuring", "circular", "mule_fanin", "mule_fanout", "layering"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_dataset(n_accounts: int = 800, n_legit_tx: int = 4000,
                     n_rings: int = 15, seed: int = 42, window_days: int = 30,
                     n_decoys: int | None = None):
    """Return (dataset, labels) dicts conforming to schemas.py §7.

    Deterministic for a given ``seed``. Always plants ONE flagship multi-stage "kingpin" ring
    (placement → layering → integration) plus ``n_rings`` single-typology rings distributed
    round-robin across the five typologies (15 → 3 each). ``n_decoys`` plants legit
    hard-negative structures; **when None (default) the count AND kinds are randomized per
    seed** so every Generate click stresses precision differently (`0` = none, N = exactly N).
    """
    rng = random.Random(seed)
    win_min = window_days * 24 * 60

    # ── accounts ──────────────────────────────────────────────────────────────
    accounts: list[dict] = []
    for i in range(1, n_accounts + 1):
        is_biz = rng.random() < 0.15
        accounts.append({
            "account_id": f"ACC{i:05d}",
            "owner_name": (rng.choice(BIZ) if is_biz
                           else f"{rng.choice(FIRST)} {rng.choice(LAST)[0]}."),
            "account_type": "business" if is_biz else "personal",
            "country": rng.choice(COUNTRIES),
            "opened_at": _iso(BASE - timedelta(days=rng.randint(60, 1200)))[:10],
            "kyc_risk": rng.choices(["low", "medium", "high"], weights=[0.8, 0.15, 0.05])[0],
            "status": "active",  # baseline enforcement state; freeze/review is runtime (TASKS §6)
        })
    acc_ids = [a["account_id"] for a in accounts]
    acc_by_id = {a["account_id"]: a for a in accounts}
    biz_ids = [a["account_id"] for a in accounts if a["account_type"] == "business"]
    personal_ids = [a["account_id"] for a in accounts if a["account_type"] == "personal"]

    txs: list[dict] = []
    counter = [0]

    def new_tx(src, dst, amount, when, channel=None):
        counter[0] += 1
        t = {"tx_id": f"TX{counter[0]:06d}", "timestamp": _iso(when),
             "src": src, "dst": dst, "amount": round(float(amount), 2),
             "currency": "EUR", "channel": channel or rng.choice(CHANNELS)}
        txs.append(t)
        return t["tx_id"]

    def jitter(t0: datetime, hours: float) -> datetime:
        return t0 + timedelta(hours=hours)

    # ── legit background traffic ────────────────────────────────────────────────
    # Spread realistic flows across the whole window. These create *legit* hubs
    # (employers, merchants) with high degree — detectors must NOT flag them, because
    # their activity is spread over weeks, not bursty. Budget split:
    #   ~30% salary, ~30% merchant card spend, ~15% recurring bills, rest random P2P.
    n_salary = int(n_legit_tx * 0.30)
    n_merchant = int(n_legit_tx * 0.30)
    n_bills = int(n_legit_tx * 0.15)
    n_p2p = max(0, n_legit_tx - n_salary - n_merchant - n_bills)

    # Pick a handful of employers / merchants / utilities from the business accounts
    # (fall back to personal if too few businesses exist in a tiny dataset).
    pool = biz_ids if len(biz_ids) >= 9 else acc_ids
    employers = rng.sample(pool, min(3, len(pool)))
    merchants = rng.sample([b for b in pool if b not in employers],
                           min(4, max(1, len(pool) - len(employers)))) if len(pool) > len(employers) else []
    utilities = rng.sample([b for b in pool if b not in employers and b not in merchants],
                           min(2, max(0, len(pool) - len(employers) - len(merchants)))) \
        if len(pool) > len(employers) + len(merchants) else []
    legit_hub_ids = set(employers) | set(merchants) | set(utilities)

    # Realistic profile for legit hubs: established (old account) + clean KYC. This is the
    # *fair signal* a detector can use to separate genuine payroll/merchant fan-out from mules.
    for hid in legit_hub_ids:
        a = acc_by_id[hid]
        a["account_type"] = "business"
        a["kyc_risk"] = "low"
        a["opened_at"] = _iso(BASE - timedelta(days=rng.randint(500, 1500)))[:10]

    # Salary: each employer pays a stable roster a consistent monthly-ish wage, spread over weeks.
    if employers:
        for emp in employers:
            roster = rng.sample(personal_ids or acc_ids, min(40, len(personal_ids or acc_ids)))
            for _ in range(n_salary // len(employers)):
                worker = rng.choice(roster)
                wage = round(rng.uniform(1400, 3600), 2)
                when = BASE + timedelta(minutes=rng.randint(0, win_min))
                new_tx(emp, worker, wage, when, "sepa")

    # Merchant card spend: many customers pay merchants small amounts, spread out.
    if merchants:
        for _ in range(n_merchant):
            cust = rng.choice(personal_ids or acc_ids)
            mer = rng.choice(merchants)
            amt = round(rng.uniform(5, 250), 2)
            when = BASE + timedelta(minutes=rng.randint(0, win_min))
            new_tx(cust, mer, amt, when, "card")

    # Recurring bills: customers pay utilities modest, regular amounts.
    if utilities:
        for _ in range(n_bills):
            cust = rng.choice(personal_ids or acc_ids)
            util = rng.choice(utilities)
            amt = round(rng.uniform(20, 320), 2)
            when = BASE + timedelta(minutes=rng.randint(0, win_min))
            new_tx(cust, util, amt, when, "sepa")

    # Random P2P background — the long tail (mostly hundreds to low thousands).
    for _ in range(n_p2p):
        s, d = rng.sample(acc_ids, 2)
        amt = round(rng.lognormvariate(6.0, 0.9), 2)
        when = BASE + timedelta(minutes=rng.randint(0, win_min))
        new_tx(s, d, amt, when)

    # ── planted laundering rings ───────────────────────────────────────────────
    labels_rings: list[dict] = []
    mules: set[str] = set()
    used_central: set[str] = set()  # avoid reusing a hub as the centre of two rings

    def fresh(n: int, exclude: set[str]) -> list[str]:
        choices = [a for a in acc_ids if a not in exclude and a not in legit_hub_ids]
        return rng.sample(choices, n)

    def plant(pattern: str, idx: int) -> dict:
        ring_accts: list[str] = []
        ring_txs: list[str] = []
        ring_mules: list[str] = []
        # Each instance starts at a different point in the window for variety.
        t0 = BASE + timedelta(days=rng.randint(1, max(2, window_days - 4)),
                              hours=rng.randint(0, 18))

        if pattern == "structuring":
            # AMLSim "fan-in / smurfing": N smurfs deposit sub-threshold cash into one
            # collector within 72h; the collector then wires the consolidated sum out.
            hub = fresh(1, used_central)[0]
            srcs = fresh(rng.randint(4, 6), used_central | {hub})
            total = 0.0
            for j, s in enumerate(srcs):
                amt = rng.uniform(0.72, 0.985) * THRESHOLD
                total += amt
                ring_txs.append(new_tx(s, hub, amt, jitter(t0, j * 9 + rng.uniform(0, 4)), "cash_deposit"))
            dest = fresh(1, used_central | {hub} | set(srcs))[0]
            ring_txs.append(new_tx(hub, dest, total * rng.uniform(0.95, 0.98),
                                   jitter(t0, 50 + rng.uniform(0, 10)), "wire"))
            ring_accts = [hub] + srcs + [dest]
            ring_mules = [hub, dest]  # collector + next layer are the relays; smurfs are one-shot
            used_central.add(hub)

        elif pattern == "circular":
            # AMLSim "cycle": money loops back to its origin through 3–5 hops, timestamps
            # strictly increasing, ~0.9 retained per hop, all inside 72h.
            chain = fresh(rng.randint(3, 5), used_central)
            amt = rng.uniform(25_000, 80_000)
            n = len(chain)
            for j in range(n):
                s, d = chain[j], chain[(j + 1) % n]
                ring_txs.append(new_tx(s, d, amt * (0.92 ** j),
                                       jitter(t0, j * 12 + rng.uniform(0, 5)), "wire"))
            ring_accts = list(chain)
            ring_mules = list(chain)
            used_central.update(chain)

        elif pattern == "mule_fanin":
            # AMLSim "fan-in": many sources push funds to one mule in a tight burst (48h),
            # which then consolidates the haul onward.
            hub = fresh(1, used_central)[0]
            srcs = fresh(rng.randint(7, 12), used_central | {hub})
            collected = 0.0
            for j, s in enumerate(srcs):
                amt = rng.uniform(3_000, 9_000)
                collected += amt
                ring_txs.append(new_tx(s, hub, amt, jitter(t0, j * 3 + rng.uniform(0, 1.5))))
            dest = fresh(1, used_central | {hub} | set(srcs))[0]
            ring_txs.append(new_tx(hub, dest, collected * rng.uniform(0.9, 0.96),
                                   jitter(t0, 44 + rng.uniform(0, 6)), "wire"))
            ring_accts = [hub] + srcs + [dest]
            ring_mules = [hub, dest]
            used_central.add(hub)

        elif pattern == "mule_fanout":
            # AMLSim "fan-out": one source seeds a mule, which sprays funds to many recipients.
            hub = fresh(1, used_central)[0]
            dsts = fresh(rng.randint(7, 12), used_central | {hub})
            seed_src = fresh(1, used_central | {hub} | set(dsts))[0]
            # Each spoke is a material chunk (real fan-out distributes sizable sums, not dust).
            spokes = [rng.uniform(6_000, 13_000) for _ in dsts]
            pot = sum(spokes) * rng.uniform(1.0, 1.05)  # hub keeps a small cut
            ring_txs.append(new_tx(seed_src, hub, pot, jitter(t0, rng.uniform(0, 2)), "wire"))
            for j, (d, amt) in enumerate(zip(dsts, spokes)):
                ring_txs.append(new_tx(hub, d, amt, jitter(t0, 4 + j * 2 + rng.uniform(0, 1))))
            ring_accts = [seed_src, hub] + dsts
            ring_mules = [hub, seed_src]
            used_central.add(hub)

        elif pattern == "layering":
            # AMLSim "stack": a long relay chain moves a lump through 4–6 accounts, each
            # forwarding ~0.85 onward within hours, channels mixed (crypto/wire) to obscure.
            chain = fresh(rng.randint(4, 6), used_central)
            amt = rng.uniform(30_000, 90_000)
            for j in range(len(chain) - 1):
                ch = "crypto" if j % 2 else "wire"
                ring_txs.append(new_tx(chain[j], chain[j + 1], amt * (0.85 ** j),
                                       jitter(t0, j * 6 + rng.uniform(0, 2.5)), ch))
            ring_accts = list(chain)
            ring_mules = chain[1:-1]  # interior relays exist only to pass money through
            used_central.update(chain[1:-1])

        mules.update(ring_mules)
        return {"ring_id": f"TRUE_{idx:03d}", "account_ids": ring_accts,
                "tx_ids": ring_txs, "patterns": [pattern]}

    def plant_kingpin(idx: int) -> dict:
        """Flagship multi-stage ring — the full laundering lifecycle around one orchestrator:
        smurfs ─(sub-threshold cash)→ collector ─(layering)→ relay1 ─→ KINGPIN ─(fan-out)→ cash-outs.
        collector & relay1 each receive-then-forward (>=money-edge, single counterparty, <24h) so
        they're pass-throughs; the collector also trips structuring + fan_in; the kingpin trips
        fan_out and pays a small kickback to relay1 — that kickback makes the fan-out seed share two
        accounts with the chain, so `build_rings` merges every stage into ONE ring spanning
        structuring + fan_in + passthrough + fan_out (max pattern diversity) with the largest member
        volume. Chain kept to 2 hops so it adds only 2 pass-through findings (keeps the detector lean)."""
        smurfs = fresh(6, used_central)
        collector, relay1, kingpin = fresh(3, used_central | set(smurfs))
        cashouts = fresh(5, used_central | set(smurfs) | {collector, relay1, kingpin})
        k_txs: list[str] = []
        t0 = BASE + timedelta(days=rng.randint(3, max(4, window_days - 6)), hours=rng.randint(0, 6))

        # stage 1 — placement: 6 smurfs deposit sub-threshold cash into the collector (≈10h burst)
        pot = 0.0
        for j, s in enumerate(smurfs):
            amt = rng.uniform(0.85, 0.985) * THRESHOLD
            pot += amt
            k_txs.append(new_tx(s, collector, amt, jitter(t0, j * 1.6 + rng.uniform(0, 1)), "cash_deposit"))

        # stage 2 — layering: collector → relay1 → kingpin, each forwarding ~0.92 to a SINGLE
        # counterparty within 24h (pass-through shape)
        amt = pot * rng.uniform(0.90, 0.95)
        k_txs.append(new_tx(collector, relay1, amt, jitter(t0, 16 + rng.uniform(0, 4)), "wire"))
        amt *= rng.uniform(0.90, 0.95)
        k_txs.append(new_tx(relay1, kingpin, amt, jitter(t0, 30 + rng.uniform(0, 4)), "crypto"))

        # stage 3 — integration: kingpin fans the laundered sum out to cash-out mules (≥€5k chunks),
        # plus a kickback to relay1 (the lieutenant's cut) which also bridges the fan-out into the ring
        targets = [relay1] + cashouts
        each = amt / len(targets)
        for j, c in enumerate(targets):
            k_txs.append(new_tx(kingpin, c, each * rng.uniform(0.95, 1.05),
                                jitter(t0, 44 + j * 1.5 + rng.uniform(0, 1)), "wire"))

        spine = [collector, relay1, kingpin]
        used_central.update(spine)
        mules.update(spine)  # the orchestration spine are the mules; smurfs/cash-outs are one-shot
        return {"ring_id": f"TRUE_{idx:03d}",
                "account_ids": smurfs + spine + cashouts, "tx_ids": k_txs,
                "patterns": ["structuring", "layering", "mule_fanin", "mule_fanout"]}

    # Flagship kingpin first (reserves clean accounts), then n_rings single-typology rings.
    labels_rings.append(plant_kingpin(1))
    order = [PATTERNS[i % len(PATTERNS)] for i in range(max(1, n_rings))]
    for idx, pattern in enumerate(order, start=2):
        labels_rings.append(plant(pattern, idx))

    # Realistic profile for mule *centres*: freshly opened + elevated KYC risk — the way real
    # laundering uses throwaway accounts. (Peripheral smurfs keep their background profile.)
    for mid in mules:
        a = acc_by_id[mid]
        a["kyc_risk"] = rng.choices(["medium", "high"], weights=[0.45, 0.55])[0]
        a["opened_at"] = _iso(BASE - timedelta(days=rng.randint(8, 130)))[:10]
        a["country"] = rng.choice(HIGH_RISK_CC)

    # ── hard-negative decoys (NOT labelled) ─────────────────────────────────────
    # Legit structures that *look* like laundering to a naive detector. A robust detector
    # should separate them using their legit signature (business + low-KYC + aged + a CY/GR/GB
    # jurisdiction), which we stamp on the decoy "actor" accounts below. Any flag here is a
    # genuine false-positive — that's the point: it makes precision earned, not given.
    ring_participants = mules | {a for r in labels_rings for a in r["account_ids"]}
    decoy_actors: set[str] = set()
    DECOYS = ["payroll_burst", "merchant_burst", "b2b_subthreshold", "settlement_loop"]

    def pick_biz(n: int, exclude: set[str]) -> list[str]:
        cands = [b for b in biz_ids if b not in exclude] or [a for a in acc_ids if a not in exclude]
        return rng.sample(cands, min(n, len(cands)))

    # Dynamic by default: a random count AND a random kind per decoy, so each seed (every live
    # "Generate" click) stresses precision with a different hard-negative mix. Explicit N is honored.
    decoy_count = rng.randint(5, 12) if n_decoys is None else max(0, n_decoys)
    for k in range(decoy_count):
        kind = rng.choice(DECOYS)
        t0 = BASE + timedelta(days=rng.randint(1, max(2, window_days - 3)), hours=rng.randint(0, 18))

        if kind == "payroll_burst":
            # Real payday: an employer pays its whole roster inside ~24h → looks like fan-out.
            emp = pick_biz(1, ring_participants | decoy_actors)[0]
            roster = rng.sample(personal_ids or acc_ids, min(rng.randint(25, 35), len(personal_ids or acc_ids)))
            for j, w in enumerate(roster):
                new_tx(emp, w, rng.uniform(1_400, 3_600), jitter(t0, rng.uniform(0, 24)), "sepa")
            decoy_actors.add(emp)

        elif kind == "merchant_burst":
            # Flash sale / event day: many customers pay one merchant in ~36h → looks like fan-in.
            mer = pick_biz(1, ring_participants | decoy_actors)[0]
            custs = rng.sample(personal_ids or acc_ids, min(rng.randint(20, 30), len(personal_ids or acc_ids)))
            for c in custs:
                new_tx(c, mer, rng.uniform(20, 300), jitter(t0, rng.uniform(0, 36)), "card")
            decoy_actors.add(mer)

        elif kind == "b2b_subthreshold":
            # Legit wholesaler paid by several clients in just-under-€10k invoices within 72h →
            # looks like structuring (receiver gathers multiple sub-threshold credits).
            recv = pick_biz(1, ring_participants | decoy_actors)[0]
            payers = pick_biz(rng.randint(3, 5), ring_participants | decoy_actors | {recv})
            for j, p in enumerate(payers):
                new_tx(p, recv, rng.uniform(7_000, 9_500), jitter(t0, j * 14 + rng.uniform(0, 8)), "sepa")
            decoy_actors.update([recv] + payers)

        elif kind == "settlement_loop":
            # Inter-company treasury settlement: 3 group companies net off in a loop within 72h,
            # value largely retained → looks like a circular-flow ring (the hardest negative).
            grp = pick_biz(3, ring_participants | decoy_actors)
            if len(grp) == 3:
                amt = rng.uniform(20_000, 60_000)
                for j in range(3):
                    new_tx(grp[j], grp[(j + 1) % 3], amt * (0.97 ** j),
                           jitter(t0, j * 16 + rng.uniform(0, 6)), "wire")
                decoy_actors.update(grp)

    # Stamp the decoy actors with a clean, established profile (the fair separating signal).
    for did in decoy_actors:
        a = acc_by_id[did]
        a["account_type"] = "business"
        a["kyc_risk"] = "low"
        a["opened_at"] = _iso(BASE - timedelta(days=rng.randint(500, 1500)))[:10]
        a["country"] = rng.choice(["CY", "CY", "GR", "GB", "DE"])

    rng.shuffle(txs)  # so planted txns aren't clustered at the end of the stream
    dataset = {"accounts": accounts, "transactions": txs}
    labels = {"mule_accounts": sorted(mules), "rings": labels_rings}
    return dataset, labels


# ── live streaming engine (demo "live feed" mode) ────────────────────────────
class LiveFeed:
    """Stateful generator for the demo's LIVE mode.

    Unlike `generate_dataset` (a fixed batch), this models an *ongoing* monitored stream:
    `initial()` lays down a small starting network (~100 transactions), then each `next_batch()`
    advances a virtual clock and emits a handful of BRAND-NEW transactions — mostly legitimate
    traffic, with the occasional freshly-planted laundering burst — so the UI can poll it every
    1–10s and watch the network (and new rings) form in real time.

    Self-contained and additive — it does NOT touch `generate_dataset`, the committed
    `sample_data/`, or the detection pipeline, so existing metrics/tests are unaffected. The
    network **grows over time**: new legit accounts open at random intervals and each laundering
    ring is built from BRAND-NEW accounts, so `next_batch()` also returns those new accounts
    (caller appends them to its dataset before re-detecting). All emitted objects honor the
    frozen schemas.

    Anti-merge guarantee: legit traffic only ever flows between *legit* accounts, and each ring
    is minted on its own fresh accounts — so distinct rings can never share or be bridged into
    one another (no mega-ring).
    """

    # small laundering bursts the stream can inject live (kept short so they complete in one batch)
    BURSTS = ("structuring", "fan_in", "cycle")

    def __init__(self, seed: int | None = None, n_accounts: int = 60):
        self.rng = random.Random(seed)
        self.clock = BASE
        self._n = 0            # tx counter
        self._acct_n = 0       # account-id counter (continues as new accounts are minted)
        self._ring_n = 0
        self._new_accts: list[dict] = []           # accounts minted during the current batch
        self._legit_ids: list[str] = []            # legit pool (grows as new customers open accounts)
        self._legit_acct_in = self.rng.randint(1, 10)  # ticks until the next legit account opens
        self.accounts: list[dict] = []
        for _ in range(n_accounts):                # small starting pool of established legit customers
            self._mint("legit", opened_days=self.rng.randint(60, 1200))
        self._new_accts = []                       # the starting pool isn't "new" — clear the buffer

    def _mint(self, profile: str, opened_days: int | None = None) -> str:
        """Create a new account (legit or mule), append it to the network, and record it as new.
        `opened_days` ago, else opened *now* (the stream clock) — a freshly opened account is itself
        a risk signal. Returns the new account id."""
        self._acct_n += 1
        aid = f"ACC{self._acct_n:05d}"
        opened = (BASE - timedelta(days=opened_days)) if opened_days is not None else self.clock
        if profile == "mule":
            acct = {"account_id": aid,
                    "owner_name": f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)[0]}.",
                    "account_type": "personal",
                    "country": self.rng.choice(HIGH_RISK_CC),
                    "opened_at": _iso(opened)[:10],
                    "kyc_risk": self.rng.choices(["medium", "high"], weights=[0.45, 0.55])[0],
                    "status": "active"}
        else:  # legit
            is_biz = self.rng.random() < 0.15
            acct = {"account_id": aid,
                    "owner_name": (self.rng.choice(BIZ) if is_biz
                                   else f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)[0]}."),
                    "account_type": "business" if is_biz else "personal",
                    "country": self.rng.choice(COUNTRIES),
                    "opened_at": _iso(opened)[:10],
                    "kyc_risk": self.rng.choices(["low", "medium", "high"], weights=[0.8, 0.15, 0.05])[0],
                    "status": "active"}
            self._legit_ids.append(aid)   # only legit accounts ever carry background traffic
        self.accounts.append(acct)
        self._new_accts.append(acct)
        return aid

    def _tx(self, src, dst, amount, channel=None) -> dict:
        self._n += 1
        return {"tx_id": f"TX{self._n:06d}", "timestamp": _iso(self.clock),
                "src": src, "dst": dst, "amount": round(float(amount), 2),
                "currency": "EUR", "channel": channel or self.rng.choice(CHANNELS)}

    def _legit(self, k: int) -> list[dict]:
        out = []
        for _ in range(k):
            self.clock += timedelta(seconds=self.rng.randint(20, 240))
            s, d = self.rng.sample(self._legit_ids, 2)   # legit pool only — never touches ring accounts
            out.append(self._tx(s, d, round(self.rng.lognormvariate(6.0, 0.9), 2)))
        return out

    def _burst(self) -> tuple[list[dict], dict]:
        """Plant one short laundering burst on BRAND-NEW minted accounts (disjoint by construction)."""
        kind = self.rng.choice(self.BURSTS)
        txs: list[dict] = []
        if kind == "structuring":
            members = [self._mint("mule") for _ in range(self.rng.randint(5, 7))]
            hub, srcs = members[0], members[1:]
            for s in srcs:
                self.clock += timedelta(seconds=self.rng.randint(15, 90))
                txs.append(self._tx(s, hub, self.rng.uniform(0.75, 0.98) * THRESHOLD, "cash_deposit"))
            accts, mule = members, [hub]
        elif kind == "fan_in":
            members = [self._mint("mule") for _ in range(self.rng.randint(7, 10))]
            hub, srcs = members[0], members[1:]
            for s in srcs:
                self.clock += timedelta(seconds=self.rng.randint(10, 70))
                txs.append(self._tx(s, hub, self.rng.uniform(3_000, 9_000)))
            accts, mule = members, [hub]
        else:  # cycle
            chain = [self._mint("mule") for _ in range(self.rng.randint(3, 4))]
            amt = self.rng.uniform(20_000, 60_000)
            for j in range(len(chain)):
                self.clock += timedelta(seconds=self.rng.randint(20, 120))
                txs.append(self._tx(chain[j], chain[(j + 1) % len(chain)], amt * (0.92 ** j), "wire"))
            accts, mule = list(chain), list(chain)
        self._ring_n += 1
        ring = {"ring_id": f"LIVE_{self._ring_n:03d}", "account_ids": accts,
                "tx_ids": [t["tx_id"] for t in txs], "patterns": [kind], "mule_accounts": mule}
        return txs, ring

    def initial(self, n_tx: int = 100) -> tuple[dict, dict]:
        """Starting network: ~`n_tx` legit transactions + one obvious planted ring to anchor the view."""
        txs = self._legit(max(0, n_tx - 8))
        burst_txs, ring = self._burst()
        txs.extend(burst_txs)
        self.rng.shuffle(txs)
        # Return a COPY of the accounts list: the engine keeps mutating its own `self.accounts`
        # as it mints, so handing out the live reference would silently grow the caller's dataset
        # and double-add when it also appends `next_batch()["accounts"]`. The copy makes the
        # contract clean — `initial()` is a snapshot; `next_batch().accounts` are strictly new.
        dataset = {"accounts": list(self.accounts), "transactions": txs}
        labels = {"mule_accounts": sorted(ring.pop("mule_accounts")), "rings": [ring]}
        self._new_accts = []   # everything so far is in `dataset`; next_batch reports only newer ones
        return dataset, labels

    def next_batch(self) -> dict:
        """One tick of the live stream. Mostly new legit transactions; new legit accounts open at
        random 1–10-tick intervals; ~25% of ticks also plant a fresh laundering ring (on new
        accounts). Returns {accounts:[...new...], transactions:[...new...], ring: <new>|None, clock}
        — the caller appends the new accounts + transactions before re-running detection."""
        self._new_accts = []
        self._legit_acct_in -= 1
        if self._legit_acct_in <= 0:                       # a few new customers open accounts (calm trickle)
            for _ in range(self.rng.randint(1, 3)):
                self._mint("legit")
            self._legit_acct_in = self.rng.randint(1, 10)
        txs = self._legit(self.rng.randint(3, 9))
        ring = None
        if self.rng.random() < 0.25:
            burst_txs, ring = self._burst()
            ring["_mule_accounts"] = ring.pop("mule_accounts")   # caller may fold into labels
            txs.extend(burst_txs)
        self.rng.shuffle(txs)
        return {"accounts": list(self._new_accts), "transactions": txs,
                "ring": ring, "clock": _iso(self.clock)}


def main():
    p = argparse.ArgumentParser(description="Generate MuleNet synthetic dataset")
    p.add_argument("--accounts", type=int, default=800)
    p.add_argument("--legit-tx", type=int, default=4000)
    p.add_argument("--rings", type=int, default=15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--window-days", type=int, default=30)
    p.add_argument("--decoys", type=int, default=None,
                   help="legit hard-negative structures (unlabelled); omit = random count+kinds, 0 = none")
    p.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "sample_data"))
    a = p.parse_args()

    dataset, labels = generate_dataset(a.accounts, a.legit_tx, a.rings, a.seed, a.window_days, a.decoys)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset.json").write_text(json.dumps(dataset, indent=2))
    (out / "labels.json").write_text(json.dumps(labels, indent=2))

    from collections import Counter
    by_pat = Counter(p for r in labels["rings"] for p in r["patterns"])
    decoys_desc = "random" if a.decoys is None else a.decoys
    print(f"Wrote {len(dataset['accounts'])} accounts, {len(dataset['transactions'])} txns, "
          f"{len(labels['rings'])} rings ({len(labels['mule_accounts'])} mules), "
          f"{decoys_desc} decoys -> {out}")
    print("  rings by pattern:", dict(by_pat), "(incl. 1 flagship kingpin ring)")


if __name__ == "__main__":
    main()
