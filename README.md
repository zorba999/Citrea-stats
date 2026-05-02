# Citrea Stats

A Python script that pulls onchain stats from Citrea mainnet and testnet.

## What it does

**Part 1 — Mainnet activity stats**
Scans all mainnet transactions and counts how many unique addresses have sent 10+, 20+, 50+, 100+, 200+, 500+, or 1000+ transactions.

**Part 2 — Cross-chain stats (NFT holders)**
Fetches all holders of the [BapperQuest NFT](https://explorer.testnet.citrea.xyz/token/0x425EAcda57DBB68c7eEC250759AA9A5573Cc5540) on testnet (26,200 addresses), then checks how many of them are also active on mainnet — broken down by the same transaction thresholds.

## Sample output

```
MAINNET STATS -- Addresses by Sent-Tx Count
=======================================================
  Total unique senders on mainnet : 12,XXX

  Threshold          Addresses     % of total
  ------------------ ------------ -----------
  10+  txs               X,XXX       XX.XX%
  20+  txs               X,XXX       XX.XX%
  50+  txs               X,XXX       XX.XX%
  100+  txs                XXX        X.XX%
  200+  txs                XXX        X.XX%
  500+  txs                 XX        X.XX%
  1000+  txs                XX        X.XX%

CROSS-CHAIN STATS -- Testnet NFT (BapperQuest) + Mainnet Txs
=================================================================
  Total NFT holders (testnet)       : 26,200
  NFT holders with 1+ mainnet txs   : 5,288 (20.2%)

  Threshold                   Addresses   % of NFT holders
  -------------------------- ----------- -----------------
  NFT + 10+  mainnet txs         2,986            11.40%
  NFT + 20+  mainnet txs         1,828             6.98%
  NFT + 50+  mainnet txs           626             2.39%
  NFT + 100+  mainnet txs          376             1.44%
  NFT + 200+  mainnet txs          178             0.68%
  NFT + 500+  mainnet txs           71             0.27%
  NFT + 1000+  mainnet txs          12             0.05%
```

## Setup

**Requirements:** Python 3.8+

```bash
pip install aiohttp
```

## Usage

```bash
# Full run — mainnet scan + NFT cross-chain stats (~40-60 min first time)
python citrea_stats.py

# Only cross-chain NFT stats (~10-15 min first time)
python citrea_stats.py --only-nft

# Use cached data — instant if you already ran it before
python citrea_stats.py --no-scan
```

## How it works

| Step | What happens |
|------|-------------|
| 1 | Paginates through the [testnet explorer API](https://explorer.testnet.citrea.xyz) to collect all NFT holders |
| 2 | Paginates through all mainnet transactions via the [mainnet explorer API](https://explorer.mainnet.citrea.xyz) to build a per-sender count |
| 3 | Calls `eth_getTransactionCount` on the Citrea mainnet RPC for each NFT holder address |
| 4 | Aggregates and prints both stat tables |

Progress is saved automatically to `citrea_cache.json` after every 500 pages. If the script is interrupted, re-running it will resume from where it left off.

## Networks

| Network | RPC | Explorer |
|---------|-----|----------|
| Mainnet | https://rpc.mainnet.citrea.xyz | https://explorer.mainnet.citrea.xyz |
| Testnet | https://rpc.testnet.citrea.xyz | https://explorer.testnet.citrea.xyz |
