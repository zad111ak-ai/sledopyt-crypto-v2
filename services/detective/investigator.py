"""
Глубокое расследование токенов — TokenInvestigator.
Ищет паттерны серийных скамеров через Etherscan/DexScreener/SolanaFM.
"""
import os
import json
import time
import asyncio
import httpx
import logging

log = logging.getLogger(__name__)

PROXY = os.environ.get("HTTP_PROXY", "http://127.0.0.1:1082")
TIMEOUT = httpx.Timeout(15.0, connect=10.0)

EVM_API = {
    "ethereum": ("https://api.etherscan.io/api", "ETHERSCAN_API_KEY"),
    "bsc": ("https://api.bscscan.com/api", "BSCSCAN_API_KEY"),
    "polygon": ("https://api.polygonscan.com/api", "POLYGONSCAN_API_KEY"),
    "base": ("https://api.basescan.org/api", "BASESCAN_API_KEY"),
    "arbitrum": ("https://api.arbiscan.io/api", "ARBISCAN_API_KEY"),
}


class TokenInvestigator:
    """Расследователь токенов — находит серийных скамеров."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(proxy=PROXY, timeout=TIMEOUT)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ─── ГЛАВНЫЙ МЕТОД ────────────────────────────────────────

    async def investigate(self, address: str, chain: str) -> dict:
        """Полное расследование токена."""

        # Шаг 1: Создатель
        creator = await self._get_creator(address, chain)

        # Шаг 2-4: Параллельные задачи
        siblings_task = asyncio.create_task(
            self._find_sibling_tokens(creator, chain) if creator else _empty_list()
        )
        current_data_task = asyncio.create_task(
            self._get_token_data(address, chain)
        )
        scam_connections_task = asyncio.create_task(
            self._find_scam_connections(address, chain)
        )

        siblings, current_data, scam_connections = await asyncio.gather(
            siblings_task, current_data_task, scam_connections_task,
            return_exceptions=True,
        )

        # Обработка ошибок
        if isinstance(siblings, Exception):
            log.warning(f"siblings error: {siblings}")
            siblings = []
        if isinstance(current_data, Exception):
            log.warning(f"current_data error: {current_data}")
            current_data = None
        if isinstance(scam_connections, Exception):
            log.warning(f"scam_connections error: {scam_connections}")
            scam_connections = []

        # Шаг 5: Анализ siblings
        dead_count = await self._count_dead_siblings(siblings)

        # Шаг 6: Вердикт
        return self._calculate_verdict(
            creator=creator,
            siblings=siblings,
            dead_count=dead_count,
            current_data=current_data,
            scam_connections=scam_connections,
        )

    # ─── СОЗДАТЕЛЬ КОНТРАКТА ─────────────────────────────────

    async def _get_creator(self, address: str, chain: str) -> str | None:
        if chain in EVM_API:
            return await self._get_creator_evm(address, chain)
        elif chain == "solana":
            return await self._get_creator_solana(address)
        elif chain == "ton":
            return await self._get_creator_ton(address)
        return None

    async def _get_creator_evm(self, address: str, chain: str) -> str | None:
        url, env_key = EVM_API[chain]
        api_key = os.environ.get(env_key, "")
        try:
            client = await self._get_client()
            r = await client.get(url, params={
                "module": "contract",
                "action": "getcontractcreation",
                "contractaddresses": address,
                "apikey": api_key,
            })
            data = r.json()
            result = data.get("result", [])
            if result and isinstance(result, list):
                return result[0].get("contractCreator")
        except Exception as e:
            log.warning(f"get_creator_evm error ({chain}): {e}")
        return None

    async def _get_creator_solana(self, mint: str) -> str | None:
        try:
            client = await self._get_client()
            r = await client.get(f"https://api.solana.fm/v0/tokens/{mint}")
            if r.status_code == 200:
                data = r.json()
                return data.get("tokenInfo", {}).get("mintAuthority")
        except Exception as e:
            log.warning(f"get_creator_solana error: {e}")
        return None

    async def _get_creator_ton(self, address: str) -> str | None:
        try:
            client = await self._get_client()
            r = await client.get(f"https://tonapi.io/v2/jettons/{address}")
            if r.status_code == 200:
                data = r.json()
                return data.get("admin", {}).get("address")
        except Exception as e:
            log.warning(f"get_creator_ton error: {e}")
        return None

    # ─── СИБЛИНГ-ТОКЕНЫ ──────────────────────────────────────

    async def _find_sibling_tokens(self, creator: str, chain: str) -> list[dict]:
        if chain in EVM_API:
            return await self._find_evm_siblings(creator, chain)
        return []

    async def _find_evm_siblings(self, creator: str, chain: str) -> list[dict]:
        url, env_key = EVM_API[chain]
        api_key = os.environ.get(env_key, "")
        try:
            client = await self._get_client()
            r = await client.get(url, params={
                "module": "account",
                "action": "txlist",
                "address": creator,
                "startblock": 0,
                "endblock": 99999999,
                "page": 1,
                "offset": 100,
                "sort": "asc",
                "apikey": api_key,
            })
            data = r.json()
            siblings = []
            for tx in data.get("result", []):
                if tx.get("contractAddress") and tx.get("to") == "":
                    siblings.append({
                        "address": tx["contractAddress"],
                        "chain": chain,
                        "created_at": int(tx.get("timeStamp", 0)),
                    })
            return siblings[:15]  # Топ-15
        except Exception as e:
            log.warning(f"find_evm_siblings error: {e}")
            return []

    # ─── ДАННЫЕ ТОКЕНА ───────────────────────────────────────

    async def _get_token_data(self, address: str, chain: str) -> dict | None:
        try:
            client = await self._get_client()
            r = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{address}"
            )
            if r.status_code != 200:
                return None
            pairs = r.json().get("pairs", [])
            if not pairs:
                return None
            pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            return {
                "symbol": pair.get("baseToken", {}).get("symbol", "?"),
                "name": pair.get("baseToken", {}).get("name", ""),
                "price": float(pair.get("priceUsd", 0) or 0),
                "liquidity": float(pair.get("liquidity", {}).get("usd", 0) or 0),
                "volume_24h": float(pair.get("volume", {}).get("h24", 0) or 0),
                "price_change_24h": float(pair.get("priceChange", {}).get("h24", 0) or 0),
                "created_at": pair.get("pairCreatedAt", 0),
            }
        except Exception as e:
            log.warning(f"get_token_data error: {e}")
            return None

    async def _count_dead_siblings(self, siblings: list[dict]) -> int:
        dead = 0
        for sib in siblings:
            data = await self._get_token_data(sib["address"], sib["chain"])
            if not data:
                dead += 1
                continue
            if (data["liquidity"] < 1000
                    or data["volume_24h"] < 100
                    or data["price_change_24h"] < -90):
                dead += 1
        return dead

    # ─── СВЯЗИ СО СКАМАМИ ────────────────────────────────────

    async def _find_scam_connections(self, address: str, chain: str) -> list[dict]:
        import db
        known_scams = db.fetchall(
            """SELECT token_address, chain, evidence FROM scam_reports
               WHERE status = 'confirmed' AND chain = ?
               ORDER BY created_at DESC LIMIT 10""",
            (chain,),
        )
        if not known_scams:
            return []

        current_holders = await self._get_top_holders(address, chain)
        if not current_holders:
            return []

        connections = []
        for scam in known_scams:
            scam_holders = await self._get_top_holders(scam["token_address"], scam["chain"])
            common = set(current_holders) & set(scam_holders)
            if common:
                connections.append({
                    "scam_address": scam["token_address"],
                    "common_holders": list(common)[:5],
                    "evidence": scam.get("evidence", ""),
                })
        return connections

    async def _get_top_holders(self, address: str, chain: str) -> list[str]:
        if chain in EVM_API:
            return await self._get_evm_holders(address, chain)
        return []

    async def _get_evm_holders(self, address: str, chain: str) -> list[str]:
        # Используем Etherscan token holder list (бесплатно)
        url, env_key = EVM_API[chain]
        api_key = os.environ.get(env_key, "")
        try:
            client = await self._get_client()
            r = await client.get(url, params={
                "module": "token",
                "action": "tokenholderlist",
                "contractaddress": address,
                "page": 1,
                "offset": 20,
                "apikey": api_key,
            })
            data = r.json()
            holders = []
            for h in data.get("result", []):
                holders.append(h.get("TokenHolderAddress", "").lower())
            return holders
        except Exception:
            return []

    # ─── ВЕРДИКТ ─────────────────────────────────────────────

    def _calculate_verdict(
        self, creator, siblings, dead_count, current_data, scam_connections
    ) -> dict:
        score = 0
        red_flags = []

        # Флаг 1: Много мёртвых siblings
        if len(siblings) >= 3:
            dead_ratio = dead_count / len(siblings)
            if dead_ratio > 0.7:
                score += 40
                red_flags.append(f"🚨 {dead_count}/{len(siblings)} токенов создателя мертвы")
            elif dead_ratio > 0.4:
                score += 20
                red_flags.append(f"⚠️ {dead_count}/{len(siblings)} мёртвых токенов")

        # Флаг 2: Связи со скамами
        if scam_connections:
            score += 30
            total_common = sum(len(c["common_holders"]) for c in scam_connections)
            red_flags.append(
                f"🔗 {total_common} общих холдеров с {len(scam_connections)} скамами"
            )

        # Флаг 3: Подозрительный токен
        if current_data:
            if current_data.get("liquidity", 0) < 10000:
                score += 10
                red_flags.append(f"💧 Ликвидность: ${current_data['liquidity']:,.0f}")
            age_days = (time.time() * 1000 - current_data.get("created_at", 0)) / (86400 * 1000)
            if age_days < 3:
                score += 5
                red_flags.append(f"⏱ Токену всего {int(age_days)} дн.")

        # Вердикт
        if score >= 70:
            verdict = ("🚨 СЕРИЙНЫЙ СКАМЕР", "danger")
        elif score >= 40:
            verdict = ("⚠️ ПОДОЗРИТЕЛЬНО", "warning")
        else:
            verdict = ("✅ ЧИСТО", "safe")

        return {
            "creator": creator,
            "siblings_count": len(siblings),
            "dead_count": dead_count,
            "scam_connections": scam_connections,
            "scam_probability": min(100, score),
            "verdict": verdict,
            "red_flags": red_flags,
            "current_data": current_data,
        }


async def _empty_list():
    return []
