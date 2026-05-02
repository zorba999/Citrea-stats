#!/usr/bin/env python3
"""
Citrea Stats Script
====================
1) Mainnet: 3dad addresses li 3endhom +10/20/50/100/200/500/1000 transactions
2) Cross-chain: holders dyal testnet NFT li 3endhom mainnet transactions
"""

import asyncio
import aiohttp
import json
import os
import sys
import time
from collections import defaultdict

# ─── Config ───────────────────────────────────────────────────────────────────
MAINNET_RPC   = "https://rpc.mainnet.citrea.xyz"
MAINNET_API   = "https://explorer.mainnet.citrea.xyz/api/v2"
TESTNET_API   = "https://explorer.testnet.citrea.xyz/api/v2"
NFT_CONTRACT  = "0x425EAcda57DBB68c7eEC250759AA9A5573Cc5540"
THRESHOLDS    = [10, 20, 50, 100, 200, 500, 1000]
CONCURRENCY   = 15        # concurrent RPC calls
CACHE_FILE    = "citrea_cache.json"
DELAY         = 0.15      # seconds between paginated API calls

# ─── Cache helpers ────────────────────────────────────────────────────────────
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

# ─── Step 1: NFT holders from testnet ─────────────────────────────────────────
async def get_nft_holders(session, cache):
    if "nft_holders" in cache:
        holders = set(cache["nft_holders"])
        print(f"[cache] {len(holders):,} NFT holders loaded from cache")
        return holders

    holders = []
    url    = f"{TESTNET_API}/tokens/{NFT_CONTRACT}/holders"
    params = {"limit": 50}
    page   = 0

    print("Fetching testnet NFT holders (BapperQuest)...")
    while True:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status != 200:
                    await asyncio.sleep(2)
                    continue
                data = await r.json()
        except Exception as e:
            print(f"  [retry] {e}")
            await asyncio.sleep(2)
            continue

        for item in data.get("items", []):
            addr = item.get("address", {}).get("hash", "")
            if addr:
                holders.append(addr.lower())

        page += 1
        npp = data.get("next_page_params")
        if not npp:
            break

        # Update params from cursor
        params = {"limit": 50, **npp}

        if page % 20 == 0:
            print(f"  page {page:4d} -> {len(holders):,} holders collected")
        await asyncio.sleep(DELAY)

    print(f"  Total NFT holders: {len(holders):,}")
    cache["nft_holders"] = holders
    save_cache(cache)
    return set(holders)

# ─── Step 2: Scan mainnet transactions to count per-sender ────────────────────
async def scan_mainnet_txs(session, cache):
    """
    Paginate through ALL mainnet transactions and count how many times
    each address appears as sender. Returns dict {address: count}.
    This is the source for "mainnet stats" (question 1).
    """
    if "mainnet_tx_counts" in cache:
        tc = cache["mainnet_tx_counts"]
        print(f"[cache] mainnet tx counts loaded: {len(tc):,} unique senders")
        return tc

    # Resume partial scan if interrupted
    tx_counts  = defaultdict(int, cache.get("mainnet_tx_partial", {}))
    saved_npp  = cache.get("mainnet_tx_npp")

    url    = f"{MAINNET_API}/transactions"
    params = {"limit": 50, "filter": "validated"}
    if saved_npp:
        params.update(saved_npp)
        print(f"Resuming mainnet scan from checkpoint ({len(tx_counts):,} addrs already counted)...")
    else:
        print("Scanning ALL mainnet transactions (this takes ~20-40 min for 877K txs)...")
        print("Progress is saved every 500 pages – you can Ctrl+C and resume later.\n")

    page = 0
    start = time.time()

    while True:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status != 200:
                    await asyncio.sleep(2)
                    continue
                data = await r.json()
        except Exception as e:
            print(f"  [retry] {e}")
            await asyncio.sleep(2)
            continue

        items = data.get("items", [])
        if not items:
            break

        for tx in items:
            sender = tx.get("from", {}).get("hash", "")
            if sender:
                tx_counts[sender.lower()] += 1

        npp = data.get("next_page_params")
        page += 1

        if page % 500 == 0:
            elapsed = (time.time() - start) / 60
            print(f"  page {page:5d} | ~{page*50:,} txs scanned | "
                  f"{len(tx_counts):,} unique senders | {elapsed:.1f} min")
            cache["mainnet_tx_partial"] = dict(tx_counts)
            cache["mainnet_tx_npp"]     = npp
            save_cache(cache)

        if not npp:
            break

        params = {"limit": 50, "filter": "validated", **npp}
        await asyncio.sleep(DELAY)

    result = dict(tx_counts)
    cache["mainnet_tx_counts"] = result
    cache.pop("mainnet_tx_partial", None)
    cache.pop("mainnet_tx_npp", None)
    save_cache(cache)
    print(f"  Scan complete: {len(result):,} unique senders found")
    return result

# ─── Step 3: RPC nonce for NFT holders on mainnet ────────────────────────────
async def fetch_mainnet_nonces(session, addresses, cache):
    """
    For each address in `addresses`, call eth_getTransactionCount on mainnet.
    Returns dict {address: nonce_count}. Uses cache to avoid re-fetching.
    """
    nonce_cache = cache.get("nonce_cache", {})
    to_fetch    = [a for a in addresses if a not in nonce_cache]

    if to_fetch:
        print(f"Fetching mainnet nonce for {len(to_fetch):,} NFT holder addresses...")
        sem  = asyncio.Semaphore(CONCURRENCY)
        done = 0

        async def fetch_one(addr):
            nonlocal done
            async with sem:
                for attempt in range(4):
                    try:
                        payload = {
                            "jsonrpc": "2.0",
                            "method":  "eth_getTransactionCount",
                            "params":  [addr, "latest"],
                            "id":      1,
                        }
                        async with session.post(
                            MAINNET_RPC, json=payload,
                            timeout=aiohttp.ClientTimeout(total=15)
                        ) as r:
                            data  = await r.json()
                            count = int(data["result"], 16)
                            nonce_cache[addr] = count
                            done += 1
                            if done % 1000 == 0:
                                print(f"  {done:,}/{len(to_fetch):,} done...")
                                cache["nonce_cache"] = nonce_cache
                                save_cache(cache)
                            return
                    except Exception:
                        await asyncio.sleep(1 * (attempt + 1))
                nonce_cache[addr] = 0  # give up → assume 0

        await asyncio.gather(*[fetch_one(a) for a in to_fetch])
        cache["nonce_cache"] = nonce_cache
        save_cache(cache)
    else:
        print(f"[cache] nonce data loaded for {len(nonce_cache):,} addresses")

    return {a: nonce_cache.get(a, 0) for a in addresses}

# ─── Step 4: Print stats ──────────────────────────────────────────────────────
def print_mainnet_stats(tx_counts):
    total = len(tx_counts)
    print("\n" + "=" * 55)
    print("  MAINNET STATS -- Addresses by Sent-Tx Count")
    print("=" * 55)
    print(f"  Total unique senders on mainnet : {total:,}\n")
    print(f"  {'Threshold':<18} {'Addresses':>12}  {'% of total':>10}")
    print(f"  {'-'*18} {'-'*12}  {'-'*10}")
    for t in THRESHOLDS:
        count = sum(1 for v in tx_counts.values() if v >= t)
        pct   = count / total * 100 if total else 0
        print(f"  {str(t)+'+  txs':<18} {count:>12,}  {pct:>9.2f}%")
    print("=" * 55)

def print_cross_chain_stats(holders, nonce_map):
    n = len(holders)
    active = sum(1 for v in nonce_map.values() if v > 0)
    print("\n" + "=" * 65)
    print("  CROSS-CHAIN STATS -- Testnet NFT (BapperQuest) + Mainnet Txs")
    print("=" * 65)
    print(f"  Total NFT holders (testnet)       : {n:,}")
    print(f"  NFT holders with 1+ mainnet txs   : {active:,} "
          f"({active/n*100:.1f}%)\n")
    print(f"  {'Threshold':<26} {'Addresses':>12}  {'% of NFT holders':>16}")
    print(f"  {'-'*26} {'-'*12}  {'-'*16}")
    for t in THRESHOLDS:
        count = sum(1 for v in nonce_map.values() if v >= t)
        pct   = count / n * 100 if n else 0
        print(f"  NFT + {str(t)+'+  mainnet txs':<20} {count:>12,}  {pct:>15.2f}%")
    print("=" * 65)

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    cache = load_cache()

    # Choose which parts to run
    skip_scan = "--no-scan" in sys.argv   # use cache or skip mainnet scan
    only_nft  = "--only-nft" in sys.argv  # only cross-chain stats

    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 3, ssl=False)
    headers   = {"Content-Type": "application/json", "User-Agent": "CitreaStats/1.0"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:

        # ── Part A: General mainnet stats ──────────────────────────────────────
        if not only_nft:
            if skip_scan and "mainnet_tx_counts" not in cache:
                print("[--no-scan] No cached mainnet data — skipping mainnet stats.")
                mainnet_tx_counts = {}
            else:
                mainnet_tx_counts = await scan_mainnet_txs(session, cache)
            if mainnet_tx_counts:
                print_mainnet_stats(mainnet_tx_counts)

        # ── Part B: Cross-chain stats ──────────────────────────────────────────
        holders   = await get_nft_holders(session, cache)
        nonce_map = await fetch_mainnet_nonces(session, list(holders), cache)
        print_cross_chain_stats(holders, nonce_map)

    print(f"\n[done] Cache saved -> {CACHE_FILE}")

if __name__ == "__main__":
    print("Citrea Stats -- by @citrea_xyz")
    print("=" * 55)
    print("Usage:")
    print("  python citrea_stats.py               # full run (slow first time)")
    print("  python citrea_stats.py --no-scan     # skip mainnet tx scan")
    print("  python citrea_stats.py --only-nft    # only cross-chain stats")
    print("=" * 55 + "\n")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[interrupted] Progress saved to cache — run again to resume.")
