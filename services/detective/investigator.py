"""
Детектив — глубокое расследование токенов.
Ищет создателя, другие токены, связи со скамами.
"""
import httpx
import os
import logging

log = logging.getLogger(__name__)
PROXY = os.environ.get("HTTP_PROXY", "http://127.0.0.1:1082")
TIMEOUT = 15


async def get_contract_creator(address: str, chain: str) -> str | None:
    """Ищем создателя контракта через Etherscan/Toncenter."""
    try:
        if chain in ("ethereum", "bsc", "arbitrum"):
            api_key = os.environ.get("ETHERSCAN_API_KEY", "")
            base = {
                "ethereum": "https://api.etherscan.io",
                "bsc": "https://api.bscscan.com",
                "arbitrum": "https://api.arbiscan.io",
            }.get(chain, "https://api.etherscan.io")

            async with httpx.AsyncClient(proxy=PROXY, timeout=TIMEOUT) as client:
                r = await client.get(
                    f"{base}/api",
                    params={
                        "module": "contract",
                        "action": "getcontractcreation",
                        "contractaddresses": address,
                        "apikey": api_key,
                    },
                )
                data = r.json()
                if data.get("result") and isinstance(data["result"], list):
                    return data["result"][0].get("contractCreator")

    except Exception as e:
        log.warning(f"get_contract_creator error: {e}")

    return None


async def find_tokens_by_creator(creator: str, chain: str) -> list[dict]:
    """Ищет другие контракты, созданные тем же адресом."""
    # Упрощённо — через Etherscan token list
    if not creator:
        return []

    try:
        if chain in ("ethereum", "bsc", "arbitrum"):
            api_key = os.environ.get("ETHERSCAN_API_KEY", "")
            base = {
                "ethereum": "https://api.etherscan.io",
                "bsc": "https://api.bscscan.com",
                "arbitrum": "https://api.arbiscan.io",
            }.get(chain, "https://api.etherscan.io")

            async with httpx.AsyncClient(proxy=PROXY, timeout=TIMEOUT) as client:
                r = await client.get(
                    f"{base}/api",
                    params={
                        "module": "account",
                        "action": "txlist",
                        "address": creator,
                        "startblock": 0,
                        "endblock": 99999999,
                        "page": 1,
                        "offset": 50,
                        "sort": "desc",
                        "apikey": api_key,
                    },
                )
                data = r.json()
                # Фильтруем contract creation транзакции
                contracts = []
                if data.get("result") and isinstance(data["result"], list):
                    for tx in data["result"]:
                        if tx.get("to") == "" and tx.get("contractAddress"):
                            contracts.append({
                                "address": tx["contractAddress"],
                                "name": f"Contract {tx['contractAddress'][:8]}...",
                            })
                return contracts[:10]  # Топ-10

    except Exception as e:
        log.warning(f"find_tokens_by_creator error: {e}")

    return []


async def get_liquidity(address: str, chain: str) -> float:
    """Получает ликвидность через DexScreener."""
    try:
        async with httpx.AsyncClient(proxy=PROXY, timeout=TIMEOUT) as client:
            r = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{address}"
            )
            pairs = r.json().get("pairs", [])
            if pairs:
                return float(pairs[0].get("liquidity", {}).get("usd", 0))
    except Exception:
        pass
    return 0.0


async def investigate_token(address: str, chain: str) -> dict:
    """
    Глубокое расследование токена.
    Возвращает: { creator, other_tokens, dead_tokens, scam_probability, verdict }
    """
    # 1. Находим создателя
    creator = await get_contract_creator(address, chain)

    # 2. Ищем другие токены создателя
    other_tokens = await find_tokens_by_creator(creator, chain) if creator else []

    # 3. Проверяем каждый на "мёртвость" (низкая ликвидность)
    dead_count = 0
    for t in other_tokens[:5]:
        liq = await get_liquidity(t["address"], chain)
        if liq < 1000:
            dead_count += 1

    # 4. Расчёт scam probability
    score = 0
    total = len(other_tokens) or 1

    # Паттерн: создатель запускал много токенов
    if total >= 3:
        score += min(total * 5, 30)

    # Паттерн: мёртвые токены
    dead_ratio = dead_count / total
    if dead_ratio > 0.7:
        score += 40
    elif dead_ratio > 0.4:
        score += 20

    # Паттерн: нет создателя
    if not creator:
        score += 15

    # Паттерн: нет ликвидности у текущего
    current_liq = await get_liquidity(address, chain)
    if current_liq < 5000:
        score += 10

    score = min(100, score)

    verdict = classify_verdict(score)

    return {
        "creator": creator or "Неизвестен",
        "other_tokens": other_tokens,
        "dead_tokens": dead_count,
        "total_tokens": total,
        "current_liquidity": current_liq,
        "scam_probability": score,
        "verdict": verdict,
    }


def classify_verdict(score: int) -> tuple[str, str]:
    """Вердикт и уровень опасности."""
    if score >= 70:
        return ("🚨 СЕРИЙНЫЙ СКАМЕР", "danger")
    if score >= 40:
        return ("⚠️ ПОДОЗРИТЕЛЬНО", "warning")
    return ("✅ ЧИСТО", "safe")
