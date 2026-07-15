"""
scanner.py — Async crypto token security scanner
Uses DexScreener API for search/price data and GoPlus API for EVM security checks.
"""

import os
import re
import time
import httpx

# ---------------------------------------------------------------------------
# Proxy – all outbound requests go through the local SOCKS proxy
# ---------------------------------------------------------------------------
PROXY = os.environ.get("https_proxy", "http://127.0.0.1:1082")

# In-memory TTL cache (5 min)
_CACHE: dict = {}

# ---------------------------------------------------------------------------
# GoPlus chain-id mapping  (chain_name -> GoPlus chain_id string)
# ---------------------------------------------------------------------------
CHAIN_MAP = {
    "ethereum": "1",
    "eth": "1",
    "bsc": "56",
    "binance": "56",
    "polygon": "137",
    "matic": "137",
    "arbitrum": "42161",
    "arb": "42161",
    "avalanche": "43114",
    "avax": "43114",
    "fantom": "250",
    "ftm": "250",
    "cronos": "25",
    "cros": "25",
    "harmony": "1666600000",
    "one": "1666600000",
    "heco": "128",
    "oec": "66",
    "okc": "66",
    "smartchain": "56",
    "gnosis": "100",
    "xdai": "100",
    "base": "8453",
    "linea": "59144",
    "zksync": "324",
    "scroll": "534352",
    "blast": "81457",
    "mantle": "5000",
    "manta": "169",
    "op_bnb": "204",
    "pulsechain": "369",
    "mode": "34443",
}

# Reverse lookup: chain_id string -> canonical name
_CHAIN_ID_TO_NAME: dict[str, str] = {}
for _name, _cid in CHAIN_MAP.items():
    if _cid not in _CHAIN_ID_TO_NAME:
        _CHAIN_ID_TO_NAME[_cid] = _name

# ---------------------------------------------------------------------------
# URL / address patterns
# ---------------------------------------------------------------------------
_ADDR_RE = re.compile(r"0x[0-9a-fA-F]{40}")

_DEXSCREENER_PATTERNS = [
    re.compile(r"dexscreener\.com/([^/]+)/([^/]+)/(\w+)", re.IGNORECASE),
    re.compile(r"dexscreener\.com/(\w+)/(\w+)", re.IGNORECASE),
]

_DEDUST_PATTERNS = [
    re.compile(r"dedust\.io/assets/([A-Za-z0-9_-]+)"),
    re.compile(r"dedust\.io/(\w+)/assets/(\w+)"),
]

_STON_PATTERNS = [
    re.compile(r"ston\.fi/(\w+)/([^/?]+)"),
]


# ===== Address helpers ====================================================

def is_address(text: str) -> bool:
    """Return True if *text* looks like a contract address or a DEX-link URL."""
    text = text.strip()

    # Plain 0x address
    if _ADDR_RE.fullmatch(text):
        return True

    # DexScreener URL
    if "dexscreener.com" in text.lower():
        return True

    # DeDust URL
    if "dedust.io" in text.lower():
        return True

    # STON.fi URL
    if "ston.fi" in text.lower():
        return True

    return False


def extract_address(text: str) -> dict:
    """
    Extract a contract address and chain name from free-form text / URL.

    Returns  {"address": ..., "chain": ...}  or {} on failure.
    Chain may be '' if it cannot be determined.
    """
    text = text.strip()
    result: dict[str, str] = {"address": "", "chain": ""}

    # --- 1. Plain hex address ------------------------------------------------
    m = _ADDR_RE.search(text)
    if m:
        result["address"] = m.group(0)

    # --- 2. DexScreener URL ---------------------------------------------------
    for pat in _DEXSCREENER_PATTERNS:
        dm = pat.search(text)
        if dm:
            groups = dm.groups()
            if len(groups) == 3:
                result["chain"] = groups[0]
                result["address"] = groups[2]
            elif len(groups) == 2:
                # Might be /chain/address style
                result["chain"] = groups[0]
                result["address"] = groups[1]
            break

    # --- 3. DeDust URL --------------------------------------------------------
    for pat in _DEDUST_PATTERNS:
        dm = pat.search(text)
        if dm:
            groups = dm.groups()
            if len(groups) == 2:
                result["chain"] = groups[0]
                result["address"] = groups[1]
            elif len(groups) == 1:
                result["address"] = groups[0]
            break

    # --- 4. STON.fi URL -------------------------------------------------------
    for pat in _STON_PATTERNS:
        dm = pat.search(text)
        if dm:
            groups = dm.groups()
            if len(groups) >= 2:
                result["chain"] = groups[0]
                result["address"] = groups[1]
            break

    # Normalise TON chain names
    if result["chain"].lower() in ("ton", "jetton"):
        result["chain"] = "ton"

    return result


# ===== Search ==============================================================

async def search_token(query: str) -> list[dict]:
    """
    Search DexScreener by token name / ticker.
    Returns top-5 results (deduplicated by address+chain, sorted by liquidity desc).
    """
    query = query.strip()
    if not query:
        return []

    url = f"https://api.dexscreener.com/latest/dex/search/?q={query}"

    async with httpx.AsyncClient(proxy=PROXY, timeout=20) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    pairs: list[dict] = data.get("pairs") or []
    if not pairs:
        return []

    # Deduplicate by (address, chainId)
    seen: set[tuple[str, str]] = set()
    results: list[dict] = []

    for p in pairs:
        addr = (p.get("baseToken") or {}).get("address", "")
        chain = p.get("chainId", "")
        key = (addr.lower(), chain.lower())
        if key in seen or not addr:
            continue
        seen.add(key)

        liq = 0.0
        try:
            liq = float((p.get("liquidity") or {}).get("usd", 0))
        except (ValueError, TypeError):
            pass

        price_usd = 0.0
        try:
            price_usd = float(p.get("priceUsd", 0))
        except (ValueError, TypeError):
            pass

        vol = 0.0
        try:
            vol = float((p.get("volume") or {}).get("h24", 0))
        except (ValueError, TypeError):
            pass

        dex_url = p.get("url", f"https://dexscreener.com/{chain}/{addr}")

        results.append({
            "address": addr,
            "name": (p.get("baseToken") or {}).get("name", "Unknown"),
            "symbol": (p.get("baseToken") or {}).get("symbol", "???"),
            "chain": chain,
            "price_usd": price_usd,
            "volume_24h": vol,
            "liquidity": liq,
            "dex_url": dex_url,
        })

    # ─── УМНАЯ СОРТИРОВКА ─────────────────────────────────────────
    # Приоритет: официальные/надёжные токены → сверху
    query_upper = query.upper()
    
    def _trust_score(r: dict) -> float:
        """Чем выше — тем надёжнее"""
        score = 0.0
        
        # 1. Точное совпадение тикера (DOGE ищем → DOGE, а не SCAMDOGE)
        sym = (r.get("symbol") or "").upper()
        name = (r.get("name") or "").upper()
        if sym == query_upper:
            score += 500  # Точный тикер — большой приоритет
        elif query_upper in sym:
            score += 200  # Содержит запрос в тикере
        elif query_upper in name:
            score += 100  # Содержится в имени
        
        # 2. Известные сети = выше приоритет
        TRUSTED_CHAINS = {
            "ethereum": 80, "solana": 70, "bsc": 60, "base": 55,
            "polygon": 50, "arbitrum": 50, "avalanche": 45,
            "optimism": 45, "tron": 40, "bitcoin": 30,
        }
        chain = (r.get("chain") or "").lower()
        score += TRUSTED_CHAINS.get(chain, 10)  # Неизвестная сеть = 10
        
        # 3. Ликвидность (логарифмическая шкала)
        liq = float(r.get("liquidity") or 0)
        if liq > 0:
            import math
            score += min(math.log10(liq) * 5, 100)  # Макс 100 за ликвидность
        
        # 4. Объём торгов (активность = доверие)
        vol = float(r.get("volume_24h") or 0)
        if vol > 0:
            import math
            score += min(math.log10(vol) * 3, 60)
        
        return score
    
    results.sort(key=_trust_score, reverse=True)
    return results[:5]


# ===== Security scan =======================================================

async def _fetch_goplus(address: str, chain_id: str) -> dict:
    """Fetch GoPlus security data for an EVM token (with in-memory cache)."""
    cache_key = f"goplus:{chain_id}:{address.lower()}"
    cached = _CACHE.get(cache_key)
    if cached and time.time() - cached["ts"] < 300:  # 5 min TTL
        return cached["data"]

    url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={address}"
    async with httpx.AsyncClient(proxy=PROXY, timeout=20) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    result_map = data.get("result") or {}
    addr_lower = address.lower()
    info = result_map.get(addr_lower) or {}
    _CACHE[cache_key] = {"data": info, "ts": time.time()}
    return info


async def _fetch_rugcheck(address: str) -> dict:
    """Fetch RugCheck data for Solana tokens (free API)."""
    cache_key = f"rugcheck:{address}"
    cached = _CACHE.get(cache_key)
    if cached and time.time() - cached["ts"] < 300:
        return cached["data"]

    url = f"https://api.rugcheck.xyz/v1/tokens/{address}/report"
    try:
        async with httpx.AsyncClient(proxy=PROXY, timeout=20) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        _CACHE[cache_key] = {"data": data, "ts": time.time()}
        return data
    except Exception:
        return {}


async def _fetch_ton_jetton(address: str) -> dict:
    """Fetch TON jetton data (tonapi.io, free without key)."""
    cache_key = f"ton:{address}"
    cached = _CACHE.get(cache_key)
    if cached and time.time() - cached["ts"] < 300:
        return cached["data"]

    url = f"https://tonapi.io/v2/jettons/{address}"
    try:
        async with httpx.AsyncClient(proxy=PROXY, timeout=20) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        _CACHE[cache_key] = {"data": data, "ts": time.time()}
        return data
    except Exception:
        return {}


async def _fetch_dexscreener(address: str) -> list[dict]:
    """Fetch DexScreener pair data for a token address."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
    async with httpx.AsyncClient(proxy=PROXY, timeout=20) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return data.get("pairs") or []


def _parse_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


async def scan_token(address: str) -> dict:
    """
    Full security scan for a token.

    Returns:
        {
          "success": bool,
          "metrics": { ... },
          "assessment": { ... },
          "scan_time_ms": int
        }
    """
    t0 = time.monotonic()

    address = address.strip()
    if not address:
        return {
            "success": False,
            "metrics": {},
            "assessment": {"risk_level": "unknown", "flags": ["empty address"]},
            "scan_time_ms": 0,
        }

    # ------------------------------------------------------------------
    # 1. DexScreener data (works for all chains)
    # ------------------------------------------------------------------
    dex_pairs = await _fetch_dexscreener(address)

    # Determine the most likely chain from dex pairs
    chain = ""
    if dex_pairs:
        chain = dex_pairs[0].get("chainId", "")

    # Aggregate metrics from DexScreener
    total_liquidity = 0.0
    total_volume_24h = 0.0
    best_price = 0.0
    dex_names: set[str] = set()
    pair_count = len(dex_pairs)

    # NEW: extended metrics from best pair
    market_cap = 0.0
    fdv = 0.0
    price_change_24h = 0.0
    price_change_6h = 0.0
    price_change_1h = 0.0
    buys_24h = 0
    sells_24h = 0
    pair_created_at = 0
    socials: list = []
    websites: list = []

    for p in dex_pairs:
        total_liquidity += _parse_float((p.get("liquidity") or {}).get("usd"))
        total_volume_24h += _parse_float((p.get("volume") or {}).get("h24"))
        price = _parse_float(p.get("priceUsd"))
        if price > 0:
            best_price = price
        dex = p.get("dexId", "")
        if dex:
            dex_names.add(dex)

        # Extended metrics from best pair (highest liquidity)
        liq = _parse_float((p.get("liquidity") or {}).get("usd"))
        if liq > total_liquidity - liq:  # this is the dominant pair
            market_cap = _parse_float(p.get("marketCap"))
            fdv = _parse_float(p.get("fdv"))
            price_change_24h = _parse_float((p.get("priceChange") or {}).get("h24"))
            price_change_6h = _parse_float((p.get("priceChange") or {}).get("h6"))
            price_change_1h = _parse_float((p.get("priceChange") or {}).get("h1"))
            txns = p.get("txns") or {}
            h24 = txns.get("h24") or {}
            buys_24h = _safe_int(h24.get("buys"))
            sells_24h = _safe_int(h24.get("sells"))
            pair_created_at = _safe_int(p.get("pairCreatedAt"))
            info = p.get("info") or {}
            socials = info.get("socials") or []
            websites = info.get("websites") or []

    # ------------------------------------------------------------------
    # 2. GoPlus data (EVM chains) + RugCheck (Solana)
    # ------------------------------------------------------------------
    goplus: dict = {}
    rugcheck: dict = {}
    chain_id = CHAIN_MAP.get(chain.lower(), "")
    is_evm = bool(chain_id)
    is_solana = chain.lower() == "solana"

    if is_evm:
        try:
            goplus = await _fetch_goplus(address, chain_id)
        except Exception:
            goplus = {}
    elif is_solana:
        try:
            rugcheck = await _fetch_rugcheck(address)
        except Exception:
            rugcheck = {}

    # TON API (for TON chain)
    ton_data: dict = {}
    is_ton = chain.lower() == "ton"
    if is_ton:
        try:
            ton_data = await _fetch_ton_jetton(address)
        except Exception:
            ton_data = {}

    # ------------------------------------------------------------------
    # 3. Build metrics dict
    # ------------------------------------------------------------------
    buy_tax = _parse_float(goplus.get("buy_tax"))
    sell_tax = _parse_float(goplus.get("sell_tax"))
    is_honeypot = goplus.get("is_honeypot") == "1"
    is_proxy = goplus.get("is_proxy") == "1"
    owner_change_balance = goplus.get("owner_change_balance") == "1"
    hidden_owner = goplus.get("hidden_owner") == "1"
    selfdestruct = goplus.get("selfdestruct") == "1"
    external_call = goplus.get("external_call") == "1"
    can_take_back_ownership = goplus.get("can_take_back_ownership") == "1"
    is_blacklist = goplus.get("is_blacklist") == "1"
    is_whitelist = goplus.get("is_whitelist") == "1"
    is_anti_whale = goplus.get("is_anti_whale") == "1"
    trading_cooldown = goplus.get("trading_cooldown") == "1"
    transfer_pausable = goplus.get("transfer_pausable") == "1"
    isOpen_source = goplus.get("is_open_source") == "1"
    slippage_modifiable = goplus.get("slippage_modifiable") == "1"
    lp_holder_count = _safe_int(goplus.get("holder_count"))
    top10_holder_rate = _parse_float(goplus.get("top_10_holder_rate"))
    total_supply = _parse_float(goplus.get("total_supply"))
    holder_count = _safe_int(goplus.get("holder_count"))

    # LP locking info from GoPlus
    lp_total = _parse_float(goplus.get("lp_total"))
    lp_locked = _parse_float(goplus.get("is_lp_locked"))  # 1 = locked
    lp_locked_rate = _parse_float(goplus.get("lp_locked_rate"))

    # RugCheck data (Solana)
    rc_score = rugcheck.get("score", 0)  # 0-1000, higher = safer
    rc_risks = rugcheck.get("risks", [])
    rc_top_holders = rugcheck.get("topHolders", [])
    rc_token_meta = rugcheck.get("tokenMeta", {})
    rc_market = rugcheck.get("market", {})

    # Convert RugCheck score to 0-100 scale
    rc_score_100 = min(100, rc_score // 10) if rc_score else 0

    # RugCheck: DON'T use topHolders length as holder count (it's only top 20)
    # Use DexScreener FDV-based estimate instead

    # RugCheck top holder rate
    if is_solana and rc_top_holders and rc_market.get("lp"):
        lp_burned_pct = rc_market.get("lp", {}).get("lpLockedPct", 0)
        if lp_burned_pct:
            lp_locked_rate = lp_burned_pct / 100

    # TON API data
    ton_holders = _safe_int(ton_data.get("holders_count"))
    ton_admin = ton_data.get("admin", {})
    ton_admin_revoked = ton_admin.get("is_suspended", False)
    ton_meta = ton_data.get("metadata", {})

    # Use TON data for holders (fixes "0 holders" bug)
    if is_ton and ton_holders > 0:
        holder_count = ton_holders

    # Use TON admin info for security
    if is_ton:
        total_supply = _parse_float(ton_data.get("total_supply"))

    metrics: dict = {
        "address": address,
        "chain": chain,
        "chain_id": chain_id,
        "price_usd": best_price,
        "liquidity_usd": total_liquidity,
        "volume_24h": total_volume_24h,
        "pair_count": pair_count,
        "dexes": sorted(dex_names),
        # GoPlus-only (empty for non-EVM)
        "is_honeypot": is_honeypot,
        "is_proxy": is_proxy,
        "hidden_owner": hidden_owner,
        "selfdestruct": selfdestruct,
        "external_call": external_call,
        "can_take_back_ownership": can_take_back_ownership,
        "owner_change_balance": owner_change_balance,
        "is_blacklist": is_blacklist,
        "is_whitelist": is_whitelist,
        "is_anti_whale": is_anti_whale,
        "trading_cooldown": trading_cooldown,
        "transfer_pausable": transfer_pausable,
        "is_open_source": isOpen_source,
        "slippage_modifiable": slippage_modifiable,
        "buy_tax": buy_tax,
        "sell_tax": sell_tax,
        "holder_count": holder_count,
        "top10_holder_rate": top10_holder_rate,
        "total_supply": total_supply,
        "lp_total": lp_total,
        "lp_locked_rate": lp_locked_rate,
        "goplus_available": is_evm and bool(goplus),
        "rugcheck_available": is_solana and bool(rugcheck),
        "rugcheck_score": rc_score_100,
        "rugcheck_risks": [r.get("name", "") for r in rc_risks[:5]],
        "ton_available": is_ton and bool(ton_data),
        "ton_holders": ton_holders,
        # NEW: extended metrics from DexScreener
        "market_cap": market_cap,
        "fdv": fdv,
        "price_change_24h": price_change_24h,
        "price_change_6h": price_change_6h,
        "price_change_1h": price_change_1h,
        "buys_24h": buys_24h,
        "sells_24h": sells_24h,
        "pair_created_at": pair_created_at,
        "socials": socials,
        "websites": websites,
    }

    # ------------------------------------------------------------------
    # 4. Risk assessment
    # ------------------------------------------------------------------
    flags: list[str] = []

    # Critical
    if is_honeypot:
        flags.append("🔴 Honeypot detected — cannot sell")
    if is_proxy and not isOpen_source:
        flags.append("🔴 Proxy contract (hidden logic)")

    # High
    if buy_tax > 10:
        flags.append(f"🟠 Buy tax unusually high: {buy_tax:.1f}%")
    if sell_tax > 10:
        flags.append(f"🟠 Sell tax unusually high: {sell_tax:.1f}%")
    if owner_change_balance:
        flags.append("🟠 Owner can change balances")
    if can_take_back_ownership:
        flags.append("🟠 Can take back ownership")
    if top10_holder_rate > 0.5:
        flags.append(f"🟠 Top-10 holders own {top10_holder_rate*100:.1f}%")

    # Medium
    if hidden_owner:
        flags.append("🟡 Hidden owner present")
    if selfdestruct:
        flags.append("🟡 Self-destruct enabled")
    if external_call:
        flags.append("🟡 External call in contract")
    if is_blacklist:
        flags.append("🟡 Blacklist function present")
    if is_whitelist:
        flags.append("🟡 Whitelist function present")
    if transfer_pausable:
        flags.append("🟡 Transfers can be paused")
    if trading_cooldown:
        flags.append("🟡 Trading cooldown active")
    if is_anti_whale:
        flags.append("🟡 Anti-whale mechanism")
    if slippage_modifiable:
        flags.append("🟡 Slippage modifiable post-deploy")

    # RugCheck flags (Solana)
    if is_solana and rc_risks:
        for risk in rc_risks[:3]:
            risk_name = risk.get("name", "Unknown")
            risk_level = risk.get("level", "info")
            if risk_level == "critical":
                flags.append(f"🔴 RugCheck: {risk_name}")
            elif risk_level == "warn":
                flags.append(f"🟠 RugCheck: {risk_name}")
            else:
                flags.append(f"⚪ RugCheck: {risk_name}")

    # Low / informational
    if not is_evm and not dex_pairs:
        flags.append("⚪ No DEX data found — unknown token")
    if total_liquidity < 1000 and total_liquidity > 0:
        flags.append("⚪ Very low liquidity (< $1,000)")
    if not isOpen_source and is_evm:
        flags.append("⚪ Contract source not verified")
    if lp_locked_rate < 0.5 and lp_locked_rate > 0:
        flags.append("⚪ LP lock rate below 50%")

    # Determine risk level
    critical_count = sum(1 for f in flags if f.startswith("🔴"))
    high_count = sum(1 for f in flags if f.startswith("🟠"))
    medium_count = sum(1 for f in flags if f.startswith("🟡"))
    total_flags = len(flags)

    if critical_count > 0:
        risk_level = "danger"
    elif high_count >= 2:
        risk_level = "high"
    elif high_count >= 1 or medium_count >= 3:
        risk_level = "medium"
    elif total_flags > 0:
        risk_level = "low"
    else:
        risk_level = "safe"

    # Score: 100 = best, 0 = worst
    score = 100
    score -= critical_count * 30
    score -= high_count * 15
    score -= medium_count * 5
    if not isOpen_source and is_evm:
        score -= 10
    score = max(0, min(100, score))

    assessment: dict = {
        "risk_level": risk_level,
        "score": score,
        "red_flags_count": total_flags,
        "critical_flags": critical_count,
        "high_flags": high_count,
        "medium_flags": medium_count,
        "flags": flags,
        "is_evm": is_evm,
    }

    elapsed = int((time.monotonic() - t0) * 1000)

    return {
        "success": True,
        "metrics": metrics,
        "assessment": assessment,
        "scan_time_ms": elapsed,
    }
