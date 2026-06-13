"""MuleNet synthetic data generator — REQUIREMENTS.md §13 (Owner: P1).

**Stdlib only** so it runs with zero installs and produces the committed fixture.
Emits realistic background traffic + planted laundering rings, with ground-truth labels.

    python -m backend.data.generator --accounts 800 --legit-tx 4000 --rings 15 --seed 42

Design goals (Phase 1):
- **2–3 instances per laundering pattern** so detectors are tested on variety, not one example.
- **Realistic legit noise** — salaries, merchant card spend, recurring bills, P2P — including
  *legit high-degree hubs* (employers, merchants) that detectors must learn NOT to flag.
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
                     n_rings: int = 15, seed: int = 42, window_days: int = 30):
    """Return (dataset, labels) dicts conforming to schemas.py §7.

    Deterministic for a given ``seed``. ``n_rings`` is distributed round-robin across the five
    typologies, so e.g. 15 → 3 of each, 6 → 2 structuring + 1 of the rest.
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

    # Distribute n_rings round-robin across the five typologies → 2–3 instances each.
    order = [PATTERNS[i % len(PATTERNS)] for i in range(max(1, n_rings))]
    for idx, pattern in enumerate(order, start=1):
        labels_rings.append(plant(pattern, idx))

    # Realistic profile for mule *centres*: freshly opened + elevated KYC risk — the way real
    # laundering uses throwaway accounts. (Peripheral smurfs keep their background profile.)
    for mid in mules:
        a = acc_by_id[mid]
        a["kyc_risk"] = rng.choices(["medium", "high"], weights=[0.45, 0.55])[0]
        a["opened_at"] = _iso(BASE - timedelta(days=rng.randint(8, 130)))[:10]
        a["country"] = rng.choice(HIGH_RISK_CC)

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
    p.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "sample_data"))
    a = p.parse_args()

    dataset, labels = generate_dataset(a.accounts, a.legit_tx, a.rings, a.seed, a.window_days)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset.json").write_text(json.dumps(dataset, indent=2))
    (out / "labels.json").write_text(json.dumps(labels, indent=2))

    from collections import Counter
    by_pat = Counter(p for r in labels["rings"] for p in r["patterns"])
    print(f"Wrote {len(dataset['accounts'])} accounts, {len(dataset['transactions'])} txns, "
          f"{len(labels['rings'])} rings ({len(labels['mule_accounts'])} mules) -> {out}")
    print("  rings by pattern:", dict(by_pat))


if __name__ == "__main__":
    main()
