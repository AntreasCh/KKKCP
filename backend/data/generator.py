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
from collections import defaultdict
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

# ── Tier C enrichment vocabularies ───────────────────────────────────────────
OCCUPATIONS = ["teacher", "engineer", "nurse", "driver", "retired", "student",
               "clerk", "chef", "electrician", "accountant", "waiter", "mechanic"]
BIZ_CATEGORIES = ["retail", "telecom", "utilities", "logistics", "construction",
                  "food_service", "healthcare", "energy", "wholesale"]
HIGH_RISK_MCC = ["crypto_exchange", "money_services", "gambling", "precious_metals"]
PURPOSES = ["salary", "savings", "business_ops", "personal_use", "investment"]

# ── Tier D enrichment vocabularies (identity / device / network / behaviour) ──
CITIES = {"CY": ["Nicosia", "Limassol", "Larnaca", "Paphos"], "GR": ["Athens", "Thessaloniki", "Patras"],
          "GB": ["London", "Manchester", "Leeds"], "DE": ["Berlin", "Munich", "Hamburg"],
          "BG": ["Sofia", "Plovdiv"], "RU": ["Moscow", "St Petersburg"], "AE": ["Dubai", "Abu Dhabi"]}
STREETS = ["Makariou Ave", "Ledra St", "Stasinou St", "Griva Digeni", "Spyrou Kyprianou",
           "High St", "Akropoleos", "Arch. Kyprianou", "Themistokli Dervi"]
MOBILE_OS = ["Android 13", "Android 14", "iOS 17", "iOS 16"]
DESKTOP_OS = ["Windows 11", "Windows 10", "macOS 14", "Ubuntu 22.04"]
DEVICE_TYPES = ["mobile", "mobile", "mobile", "desktop", "tablet"]   # mobile-weighted
CLEAN_ISPS = ["CYTA", "Cablenet", "PrimeTel", "Cosmote", "Vodafone", "OTE", "BT", "Deutsche Telekom"]
HOSTING_ISPS = ["DigitalOcean", "OVH SAS", "M247", "Hostwinds", "Choopa LLC", "Datacamp"]  # datacenter/proxy


def _mask_id(rng) -> str:
    return f"{rng.choice('ABCDEFGHKMP')}{rng.randint(100000, 999999)}***"


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

    # ── Tier B typologies (B1 activity spike, B2 dormant reactivation) ──────────
    # Appended with FRESH account ids (ACC{n_accounts+1}…) so the rest of the fixture is byte-for-
    # byte unchanged. Each ALSO carries a pass-through / fan-in shape, so the structural detectors
    # flag the mule and assemble the ring (recall + ring-recall preserved), while the temporal
    # detectors (detect/temporal.py) add the named velocity/dormancy evidence on top.
    next_idx = [n_accounts]

    def new_account(atype: str, kyc: str, age_days: int, country: str | None = None) -> str:
        next_idx[0] += 1
        aid = f"ACC{next_idx[0]:05d}"
        rec = {"account_id": aid,
               "owner_name": (rng.choice(BIZ) if atype == "business"
                              else f"{rng.choice(FIRST)} {rng.choice(LAST)[0]}."),
               "account_type": atype, "country": country or rng.choice(COUNTRIES),
               "opened_at": _iso(BASE - timedelta(days=age_days))[:10],
               "kyc_risk": kyc, "status": "active"}
        accounts.append(rec)
        acc_by_id[aid] = rec
        acc_ids.append(aid)
        return aid

    # B2 — dormant reactivation: an AGED, clean-history account wakes up and relays a lump in <24h.
    dr_t0 = BASE + timedelta(days=window_days - 4, hours=rng.randint(0, 6))
    dr_src = new_account("personal", "low", rng.randint(200, 800))
    dr_mule = new_account("personal", rng.choice(["medium", "high"]), rng.randint(1100, 2400),
                          country=rng.choice(HIGH_RISK_CC))
    dr_dst = new_account("personal", "low", rng.randint(200, 800))
    dr_amt = rng.uniform(40_000, 70_000)
    dr_txs = [new_tx(dr_src, dr_mule, dr_amt, dr_t0, "wire"),
              new_tx(dr_mule, dr_dst, dr_amt * rng.uniform(0.90, 0.96),
                     jitter(dr_t0, rng.uniform(2, 8)), "wire")]
    mules.add(dr_mule)
    labels_rings.append({"ring_id": f"TRUE_{len(labels_rings) + 1:03d}",
                         "account_ids": [dr_src, dr_mule, dr_dst], "tx_ids": dr_txs,
                         "patterns": ["layering"]})

    # B1 — activity spike: a normally-quiet account suddenly erupts in a fan-in burst.
    sp_mule = new_account("personal", rng.choice(["medium", "high"]), rng.randint(150, 600),
                          country=rng.choice(HIGH_RISK_CC))
    sp_dst = new_account("personal", "low", rng.randint(200, 800))
    sp_txs = []
    for d in rng.sample(range(1, max(4, window_days - 6)), 3):  # quiet baseline: 3 small, spread
        sp_txs.append(new_tx(sp_mule, sp_dst, rng.uniform(50, 300),
                             BASE + timedelta(days=d, hours=rng.uniform(0, 12)), "card"))
    sp_t0 = BASE + timedelta(days=window_days - 3, hours=rng.randint(0, 4))
    sp_srcs = [new_account("personal", "low", rng.randint(200, 900)) for _ in range(8)]
    burst_total = 0.0
    for j, s in enumerate(sp_srcs):                            # sudden burst: 8 senders in <24h
        amt = rng.uniform(4_000, 8_000)
        burst_total += amt
        sp_txs.append(new_tx(s, sp_mule, amt, jitter(sp_t0, j * 2 + rng.uniform(0, 1)),
                             rng.choice(["wire", "sepa"])))
    sp_txs.append(new_tx(sp_mule, sp_dst, burst_total * rng.uniform(0.90, 0.95),
                         jitter(sp_t0, 20 + rng.uniform(0, 3)), "wire"))
    mules.add(sp_mule)
    labels_rings.append({"ring_id": f"TRUE_{len(labels_rings) + 1:03d}",
                         "account_ids": [sp_mule, sp_dst] + sp_srcs, "tx_ids": sp_txs,
                         "patterns": ["mule_fanin"]})

    # C4 device-linked mule fleet: one operator runs several THIN accounts from a single device.
    # Each only receives a chunk and forwards a small partial cut slowly — so NO structural typology
    # fires (not pass-through: ratio too low; not fan: degree 1; not a burst). Behavioural detection
    # misses them entirely; ONLY the shared-device linkage (C4) catches the fleet. Labelled as mules
    # but NOT as a ring (device linkage doesn't seed rings), so ring metrics are untouched.
    device_fleet: list[str] = []
    fl_t0 = BASE + timedelta(days=window_days - 5, hours=rng.randint(0, 6))
    for k in range(5):
        m = new_account("personal", rng.choice(["medium", "high"]), rng.randint(20, 120),
                        country=rng.choice(HIGH_RISK_CC))
        src = new_account("personal", "low", rng.randint(200, 800))
        dst = new_account("personal", "low", rng.randint(200, 800))
        recv = rng.uniform(6_000, 9_000)
        new_tx(src, m, recv, jitter(fl_t0, k * 5 + rng.uniform(0, 3)), rng.choice(["wire", "sepa"]))
        new_tx(m, dst, recv * rng.uniform(0.30, 0.45),                 # partial cut, low ratio
               jitter(fl_t0, k * 5 + 48 + rng.uniform(0, 12)), "card")  # forwarded days later (slow)
        device_fleet.append(m)
        mules.add(m)

    # ── Tier C enrichment: KYC / identity / screening / device / channel fields ──
    # Computed AFTER all planting so the core fixture stays byte-for-byte identical — we only ADD
    # fields. Risk attributes correlate with mule role; a few are planted on LEGIT actors as
    # hard-negatives (a legit PEP, a legit watchlisted business) so the new signals stay precision-
    # earned. Detectors read these in scoring.py / detect/*; nothing here flags on its own.
    throughput: dict = defaultdict(float)          # actual EUR moved per account (in + out)
    for t in txs:
        throughput[t["src"]] += t["amount"]
        throughput[t["dst"]] += t["amount"]

    legit_pool = [a for a in acc_ids if a not in mules]
    pep_legit = set(rng.sample(legit_pool, min(4, len(legit_pool))))     # C1 legit PEPs (hard neg)
    wl_legit = set(rng.sample(legit_pool, min(3, len(legit_pool))))      # C1 legit watchlist (hard neg)
    sar_legit = set(rng.sample(legit_pool, min(3, len(legit_pool))))     # C2 legit prior-SAR (hard neg)
    am_legit = set(rng.sample(legit_pool, min(3, len(legit_pool))))      # C5 legit adverse-media (hard neg)

    for a in accounts:
        aid = a["account_id"]
        a["device_id"] = f"dev-{rng.randrange(16 ** 8):08x}"
        a["signup_ip"] = f"{rng.randint(2, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        # C8 contact identifiers — unique per account by construction (derived from the id), so NO
        # legit account ever shares one. Operator fleets overwrite these with a reused value below.
        a["email"] = f"{aid.lower()}@mail.example"
        a["phone"] = f"+3579{int(aid[3:]):07d}"
        a["occupation"] = rng.choice(OCCUPATIONS) if a["account_type"] == "personal" else None
        a["business_category"] = rng.choice(BIZ_CATEGORIES) if a["account_type"] == "business" else None
        a["account_purpose"] = rng.choice(PURPOSES)
        # ── Tier D common profile (identity / device / network) — same shape for everyone; the
        # risk-bearing values diverge by role in the mule/legit branches below. ──
        cc = a["country"]
        a["city"] = rng.choice(CITIES.get(cc, ["Nicosia"]))
        a["address"] = f"{rng.randint(1, 240)} {rng.choice(STREETS)}, {a['city']}"
        a["national_id"] = _mask_id(rng)
        age = rng.randint(19, 74)
        a["date_of_birth"] = _iso(BASE - timedelta(days=age * 365 + rng.randint(0, 364)))[:10]
        dtype = rng.choice(DEVICE_TYPES)
        a["device_type"] = dtype
        a["device_os"] = rng.choice(MOBILE_OS if dtype != "desktop" else DESKTOP_OS)
        a["aliases"] = []
        actual = throughput.get(aid, 0.0)
        if aid in mules:
            # mules declare a small throwaway expected volume while actually moving large sums (C3)
            a["expected_monthly_volume"] = round(rng.uniform(1_000, 3_000), 2)
            a["vpn_tor"] = rng.random() < 0.55                           # C4
            a["failed_verifications"] = rng.randint(1, 5)               # C4
            a["prior_sars"] = rng.choices([0, 1, 2, 3], weights=[0.4, 0.3, 0.2, 0.1])[0]  # C2
            a["pep"] = rng.random() < 0.15                              # C1
            a["sanctioned"] = rng.random() < 0.18                       # C1 a minority are sanctions hits
            a["watchlist"] = rng.random() < 0.30                        # C1
            a["adverse_media"] = rng.random() < 0.25                    # C5
            a["chargeback_count"] = rng.choices([0, 1, 2, 3, 4],        # C8 fraud/dispute history
                                                weights=[0.3, 0.3, 0.2, 0.13, 0.07])[0]
            # ── Tier D mule profile: throwaway identity, fraud-farm device, dirty IP, bot-like
            # behaviour, dirty history. Recruited mules skew young; values are RANGES (overlapping
            # the legit tail) so no single attribute is a perfect separator — they amplify. ──
            a["verification_level"] = rng.choices(["unverified", "basic", "full"], weights=[0.5, 0.4, 0.1])[0]
            a["date_of_birth"] = _iso(BASE - timedelta(days=rng.randint(19, 30) * 365))[:10]  # skew young
            if rng.random() < 0.25:
                a["aliases"] = [f"{rng.choice(FIRST)} {rng.choice(LAST)}"]  # known alias
            a["device_count"] = rng.randint(2, 6)                        # juggles many devices
            a["emulator"] = rng.random() < 0.35                          # fraud-farm emulator
            a["rooted_jailbroken"] = rng.random() < 0.4
            a["ip_country"] = rng.choice(HIGH_RISK_CC)                   # connects from elsewhere
            a["ip_isp"] = rng.choice(HOSTING_ISPS) if rng.random() < 0.55 else rng.choice(CLEAN_ISPS)
            a["proxy"] = rng.random() < 0.5
            a["ip_risk_score"] = round(rng.uniform(0.55, 0.98), 2)
            a["distinct_ips"] = rng.randint(3, 12)
            a["avg_session_seconds"] = rng.randint(20, 90)              # quick in-and-out
            a["logins_30d"] = rng.randint(20, 120)
            a["failed_logins_30d"] = rng.randint(3, 25)
            a["password_resets_30d"] = rng.randint(1, 6)
            a["night_activity_ratio"] = round(rng.uniform(0.35, 0.85), 2)
            a["automation_score"] = round(rng.uniform(0.45, 0.95), 2)
            a["prior_fraud"] = rng.random() < 0.3
            a["account_takeover"] = rng.random() < 0.22
            a["disputes_count"] = rng.randint(0, 6)
            a["blacklisted"] = rng.random() < 0.25
            a["linked_accounts"] = rng.randint(2, 9)
            a["historical_risk_score"] = round(rng.uniform(0.5, 0.95), 2)
            if a["account_type"] == "business":
                a["nominee_owner"] = rng.random() < 0.6                 # C5 shell-company indicator
                if rng.random() < 0.4:
                    a["business_category"] = rng.choice(HIGH_RISK_MCC)  # C7 high-risk MCC
        else:
            # ~12% of legit accounts legitimately exceed their declared estimate (a seasonal
            # business, a bonus, a house sale) — so activity-vs-profile is NOT a perfect separator.
            # This is deliberate realism: C3 must stay a capped amplifier, never a solo flag.
            under = rng.uniform(0.15, 0.45) if rng.random() < 0.12 else rng.uniform(0.8, 1.4)
            a["expected_monthly_volume"] = round(max(500.0, actual) * under, 2)
            a["vpn_tor"] = rng.random() < 0.03
            a["failed_verifications"] = rng.choices([0, 1], weights=[0.9, 0.1])[0]
            a["prior_sars"] = 1 if aid in sar_legit else 0
            a["pep"] = aid in pep_legit
            a["sanctioned"] = False                                     # sanctions hits are confirmed-bad only
            a["watchlist"] = aid in wl_legit
            a["adverse_media"] = aid in am_legit
            a["nominee_owner"] = False
            # ~8% of legit accounts carry one historic chargeback (a disputed purchase) — so a single
            # chargeback is NOT a separator; chargeback_history must stay a capped amplifier (C8).
            a["chargeback_count"] = 1 if rng.random() < 0.08 else 0
            # ── Tier D legit profile: mostly verified, own device, home IP, human behaviour, clean
            # history — but with a realistic NOISY TAIL (a few use a VPN, travel, reset a password)
            # so the new signals stay capped amplifiers, never solo flags. ──
            a["verification_level"] = rng.choices(["full", "basic", "unverified"], weights=[0.8, 0.17, 0.03])[0]
            a["device_count"] = rng.choices([1, 1, 2, 3], weights=[0.6, 0.2, 0.15, 0.05])[0]
            a["emulator"] = False
            a["rooted_jailbroken"] = rng.random() < 0.02
            a["ip_country"] = cc if rng.random() < 0.9 else rng.choice(COUNTRIES)  # occasional travel
            a["ip_isp"] = rng.choice(CLEAN_ISPS) if rng.random() < 0.97 else rng.choice(HOSTING_ISPS)
            a["proxy"] = rng.random() < 0.03
            a["ip_risk_score"] = round(rng.uniform(0.0, 0.3), 2)
            a["distinct_ips"] = rng.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
            a["avg_session_seconds"] = rng.randint(120, 900)
            a["logins_30d"] = rng.randint(2, 40)
            a["failed_logins_30d"] = rng.choices([0, 1, 2], weights=[0.8, 0.15, 0.05])[0]
            a["password_resets_30d"] = rng.choices([0, 1], weights=[0.92, 0.08])[0]
            a["night_activity_ratio"] = round(rng.uniform(0.0, 0.25), 2)
            a["automation_score"] = round(rng.uniform(0.0, 0.25), 2)
            a["prior_fraud"] = False
            a["account_takeover"] = False
            a["disputes_count"] = a["chargeback_count"]
            a["blacklisted"] = False
            a["linked_accounts"] = rng.choices([0, 1, 2], weights=[0.75, 0.18, 0.07])[0]
            a["historical_risk_score"] = round(rng.uniform(0.0, 0.3), 2)

    # C4 device linkage: the operator runs the whole fleet from ONE device/IP (shared fingerprint).
    # Only the labelled fleet mules share it, so the linkage cluster is all-bad → precision-safe.
    op_device = f"dev-{rng.randrange(16 ** 8):08x}"
    op_ip = f"{rng.randint(2, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    for mid in device_fleet:
        acc_by_id[mid]["device_id"] = op_device
        acc_by_id[mid]["signup_ip"] = op_ip

    # C8 shared-contact operator fleets: a single operator reuses ONE email + phone across the several
    # mule accounts they control — even when each account runs on its OWN device/VPN (so device/IP
    # linkage misses them). Only labelled mules share, so every linkage cluster is all-bad → precision
    # stays earned. This is what catches the thin relay/one-shot mules that trip no transaction-pattern
    # detector. Fleets are kept >= 4 so the linkage finding alone clears τ (entity resolution).
    mule_list = sorted(mules)
    rng.shuffle(mule_list)
    fleets = [mule_list[i:i + 5] for i in range(0, len(mule_list), 5)]
    if len(fleets) > 1 and len(fleets[-1]) < 4:    # fold a too-small tail into earlier fleets
        for j, mid in enumerate(fleets.pop()):
            fleets[j % len(fleets)].append(mid)
    for fi, fleet in enumerate(fleets):
        op_email = f"operator{fi:02d}@protonmail.example"
        op_phone = f"+35799{fi:06d}"
        for mid in fleet:
            acc_by_id[mid]["email"] = op_email
            acc_by_id[mid]["phone"] = op_phone

    # C7 transaction enrichment: origin geography + card payment / refund / chargeback types.
    cc_of = {a["account_id"]: a["country"] for a in accounts}
    dev_of = {a["account_id"]: a.get("device_id") for a in accounts}
    name_of = {a["account_id"]: a.get("owner_name") for a in accounts}
    for t in txs:
        src_cc = cc_of.get(t["src"])
        if t["src"] in mules and rng.random() < 0.5:                    # mules transact from elsewhere (geo mismatch)
            alts = [c for c in HIGH_RISK_CC if c != src_cc]
            t["tx_country"] = rng.choice(alts) if alts else src_cc
        else:
            t["tx_country"] = src_cc
        if t["channel"] == "card":
            r = rng.random()
            t["tx_type"] = "refund" if r < 0.04 else ("chargeback" if r < 0.055 else "payment")
            t["merchant_category"] = rng.choice(BIZ_CATEGORIES)
        else:
            t["tx_type"] = "transfer"

        # ── Tier D per-transaction enrichment: device / IP / status / reference + per-tx risk. ──
        bad_leg = t["src"] in mules or t["dst"] in mules
        t["device_id"] = dev_of.get(t["src"])
        t["ip_country"] = t["tx_country"]
        t["ip_address"] = (f"{rng.randint(2, 223)}.{rng.randint(0, 255)}."
                           f"{rng.randint(0, 255)}.{rng.randint(1, 254)}")
        t["recipient_name"] = name_of.get(t["dst"])
        t["is_international"] = bool(t["tx_country"] and src_cc and t["tx_country"] != cc_of.get(t["dst"]))
        # most payments settle; mule legs fail / reverse more often (declines, recalled funds)
        if t["tx_type"] in ("refund", "chargeback"):
            t["status"] = "reversed"
        elif bad_leg and rng.random() < 0.12:
            t["status"] = rng.choice(["failed", "reversed"])
        else:
            t["status"] = "completed"
        ref_pool = (["transfer", "invoice", "loan repayment", "gift", "services", "urgent"]
                    if bad_leg else ["salary", "invoice", "rent", "groceries", "subscription", "transfer"])
        t["reference"] = rng.choice(ref_pool)
        # per-tx risk: large + cross-border + high-risk channel + dirty wallet, on a mule leg
        rk = 0.0
        if bad_leg:
            rk += 0.35
        if t["amount"] >= 9_000:
            rk += 0.2
        if t["is_international"]:
            rk += 0.15
        if t["channel"] in ("crypto", "cash_deposit"):
            rk += 0.15
        if t.get("wallet_label") in ("mixer", "darknet", "high_risk"):
            rk += 0.3
        if t["status"] != "completed":
            rk += 0.1
        t["risk_score"] = round(min(1.0, rk), 2)

    rng.shuffle(txs)  # so planted txns aren't clustered at the end of the stream
    dataset = {"accounts": accounts, "transactions": txs}
    labels = {"mule_accounts": sorted(mules), "rings": labels_rings}
    return dataset, labels


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
