"""MuleNet synthetic data generator — REQUIREMENTS.md §13 (Owner: P1).

**Stdlib only** so it runs with zero installs and produces the committed fixture.
Generates background transactions + planted laundering rings, with ground-truth labels.

    python -m backend.data.generator --accounts 600 --legit-tx 2500 --rings 6 --seed 42

TODO(P1): make patterns richer / closer to the IBM AMLSim benchmark shape
(see REQUIREMENTS §18 — borrow credibility from a recognized AML dataset format).
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

THRESHOLD = 10_000.0
FIRST = ["Maria", "Andreas", "Elena", "Nikos", "Sofia", "Petros", "Anna", "Giorgos",
         "Christina", "Marios", "Despina", "Kostas", "Ioanna", "Panayiotis", "Eleni",
         "Dimitris", "Katerina", "Stelios", "Chloe", "Vasilis", "Savvas", "Marina"]
LAST = ["Kattimeris", "Georgiou", "Christodoulou", "Ioannou", "Konstantinou", "Petrou",
        "Nikolaou", "Charalambous", "Andreou", "Demetriou", "Pavlou", "Antoniou", "Hadji"]
COUNTRIES = ["CY", "CY", "CY", "GR", "GR", "GB", "DE", "BG", "RU", "AE"]
CHANNELS = ["sepa", "wire", "card", "crypto", "cash_deposit"]
BASE = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_dataset(n_accounts: int = 600, n_legit_tx: int = 2500,
                     n_rings: int = 6, seed: int = 42):
    """Return (dataset, labels) dicts conforming to schemas.py §7."""
    rng = random.Random(seed)

    accounts = []
    for i in range(1, n_accounts + 1):
        accounts.append({
            "account_id": f"ACC{i:05d}",
            "owner_name": f"{rng.choice(FIRST)} {rng.choice(LAST)[0]}.",
            "account_type": "business" if rng.random() < 0.15 else "personal",
            "country": rng.choice(COUNTRIES),
            "opened_at": _iso(BASE - timedelta(days=rng.randint(60, 1200)))[:10],
            "kyc_risk": rng.choices(["low", "medium", "high"], weights=[0.8, 0.15, 0.05])[0],
        })
    acc_ids = [a["account_id"] for a in accounts]

    txs: list[dict] = []
    counter = [0]

    def new_tx(src, dst, amount, when, channel=None):
        counter[0] += 1
        t = {"tx_id": f"TX{counter[0]:06d}", "timestamp": _iso(when),
             "src": src, "dst": dst, "amount": round(float(amount), 2),
             "currency": "EUR", "channel": channel or rng.choice(CHANNELS)}
        txs.append(t)
        return t["tx_id"]

    # ── legit background traffic ──
    for _ in range(n_legit_tx):
        s, d = rng.sample(acc_ids, 2)
        amt = round(rng.lognormvariate(6.0, 1.0), 2)  # mostly hundreds–low thousands
        when = BASE + timedelta(minutes=rng.randint(0, 14 * 24 * 60))
        new_tx(s, d, amt, when)

    # ── planted laundering rings ──
    labels_rings, mules = [], set()
    cycle = ["structuring", "circular", "mule_fanin", "mule_fanout", "layering"]
    for r in range(1, n_rings + 1):
        pattern = cycle[(r - 1) % len(cycle)]
        ring_accts, ring_txs = [], []
        t0 = BASE + timedelta(days=rng.randint(1, 12), hours=rng.randint(0, 12))

        if pattern == "structuring":
            hub = rng.choice(acc_ids)
            srcs = rng.sample([a for a in acc_ids if a != hub], rng.randint(4, 6))
            total = 0.0
            for j, s in enumerate(srcs):
                amt = rng.uniform(0.72, 0.99) * THRESHOLD
                total += amt
                ring_txs.append(new_tx(s, hub, amt, t0 + timedelta(hours=j * 6 + rng.uniform(0, 3)), "cash_deposit"))
            dest = rng.choice([a for a in acc_ids if a != hub])
            ring_txs.append(new_tx(hub, dest, total * 0.97, t0 + timedelta(hours=40), "wire"))
            ring_accts = [hub] + srcs
            mules.add(hub)

        elif pattern == "circular":
            chain = rng.sample(acc_ids, rng.randint(3, 4))
            amt = rng.uniform(20_000, 80_000)
            for j in range(len(chain)):
                s, d = chain[j], chain[(j + 1) % len(chain)]
                ring_txs.append(new_tx(s, d, amt * (0.9 ** j), t0 + timedelta(hours=j * 10 + rng.uniform(0, 4)), "wire"))
            ring_accts = chain
            mules.update(chain)

        elif pattern == "mule_fanin":
            hub = rng.choice(acc_ids)
            srcs = rng.sample([a for a in acc_ids if a != hub], rng.randint(7, 12))
            for j, s in enumerate(srcs):
                ring_txs.append(new_tx(s, hub, rng.uniform(2_000, 9_000), t0 + timedelta(hours=j * 2 + rng.uniform(0, 1))))
            ring_accts = [hub] + srcs
            mules.add(hub)

        elif pattern == "mule_fanout":
            hub = rng.choice(acc_ids)
            dsts = rng.sample([a for a in acc_ids if a != hub], rng.randint(7, 12))
            for j, d in enumerate(dsts):
                ring_txs.append(new_tx(hub, d, rng.uniform(2_000, 9_000), t0 + timedelta(hours=j * 2 + rng.uniform(0, 1))))
            ring_accts = [hub] + dsts
            mules.add(hub)

        elif pattern == "layering":
            chain = rng.sample(acc_ids, rng.randint(4, 5))
            amt = rng.uniform(30_000, 90_000)
            for j in range(len(chain) - 1):
                ring_txs.append(new_tx(chain[j], chain[j + 1], amt * (0.85 ** j),
                                       t0 + timedelta(hours=j * 6 + rng.uniform(0, 2)), "crypto"))
            ring_accts = chain
            mules.update(chain[1:-1])

        labels_rings.append({"ring_id": f"TRUE_{r:03d}", "account_ids": ring_accts,
                             "tx_ids": ring_txs, "patterns": [pattern]})

    rng.shuffle(txs)  # so planted txns aren't clustered at the end
    dataset = {"accounts": accounts, "transactions": txs}
    labels = {"mule_accounts": sorted(mules), "rings": labels_rings}
    return dataset, labels


def main():
    p = argparse.ArgumentParser(description="Generate MuleNet synthetic dataset")
    p.add_argument("--accounts", type=int, default=600)
    p.add_argument("--legit-tx", type=int, default=2500)
    p.add_argument("--rings", type=int, default=6)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "sample_data"))
    a = p.parse_args()

    dataset, labels = generate_dataset(a.accounts, a.legit_tx, a.rings, a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset.json").write_text(json.dumps(dataset, indent=2))
    (out / "labels.json").write_text(json.dumps(labels, indent=2))
    print(f"Wrote {len(dataset['accounts'])} accounts, {len(dataset['transactions'])} txns, "
          f"{len(labels['rings'])} rings → {out}")


if __name__ == "__main__":
    main()
