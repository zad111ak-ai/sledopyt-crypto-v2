"""
address_parser.py — Универсальный парсер адресов 20+ блокчейнов

Поддерживает:
- Bitcoin (Legacy, P2SH, SegWit, Taproot)
- Ethereum / EVM (0x...) — ETH, BSC, Polygon, Avalanche, Arbitrum, Optimism, Base, Fantom
- Solana (base58)
- TON (EQ/UQ)
- Tron (T...)
- Cardano (addr1...)
- Ripple (r...)
- Litecoin (L/M/ltc1...)
- Dogecoin (D...)
- Dash (X...)
- Zcash (t1.../zs.../u1...)
- Monero (4.../8... 95 chars)
- Stellar (G...)
- BNB Beacon (bnb1...)
- Cosmos (cosmos1...)
- NEAR (...near)
- Tezos (tz1/tz2/tz3/KT1...)
- Waves (3P...)
- Ravencoin (R...)
- Bitcoin Cash (bitcoincash:...)
- Hedera (0.0.xxxx)
- Algorand (58 base32)
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
#  РЕЗУЛЬТАТ ПАРСИНГА
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ParsedAddress:
    address: str
    chain: str
    address_type: str           # wallet, contract, unknown
    format_subtype: str         # legacy, segwit, p2sh, bech32, taproot...
    is_valid: bool = True
    is_historical: bool = False
    historical_info: Optional[dict] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
#  ИСТОРИЧЕСКИЕ АДРЕСА
# ═══════════════════════════════════════════════════════════════════

HISTORICAL_ADDRESSES = {
    # ─── BITCOIN ──────────────────────────────────────────────────
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": {
        "name": "🏠 Genesis Block Address",
        "owner": "Satoshi Nakamoto",
        "info": (
            "Первый BTC-адрес в истории. Получил награду за genesis-блок (50 BTC). "
            "Символ всей крипто-индустрии. Satoshi никогда не двигал эти монеты — "
            "один из самых священных адресов в мире крипты."
        ),
        "significance": "legendary",
        "balance_note": "~68.2 BTC (никогда не двигались)",
    },
    "1dice8EMZmqKvrGE4Qc9bUFf9PX3xaYDp": {
        "name": "🎲 SatoshiDice",
        "owner": "Первое Bitcoin-казино",
        "info": (
            "Легендарное казино 2012 года. Один из самых активных адресов ранней эры. "
            "Каждый TX был ставкой — биткоин-гемблинг в чистом виде."
        ),
        "significance": "historical",
    },

    # ─── ETHEREUM ─────────────────────────────────────────────────
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045": {
        "name": "🧠 Vitalik Buterin",
        "owner": "Vitalik Buterin",
        "info": (
            "Личный кошелёк создателя Ethereum. "
            "Часто используется для благотворительности и голосований DAO."
        ),
        "significance": "legendary",
    },
    "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe": {
        "name": "🏗 Ethereum Foundation",
        "owner": "Ethereum Foundation",
        "info": "Основной кошелёк ETH Foundation. Хранит средства на развитие экосистемы.",
        "significance": "important",
    },
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": {
        "name": "🐋 Binance Hot Wallet #7",
        "owner": "Binance Exchange",
        "info": "Один из крупнейших hot wallets Binance. Держит миллиарды долларов.",
        "significance": "important",
    },
    "0x00000000219ab540356cBB839Cbe05303d7705Fa": {
        "name": "🔒 ETH 2.0 Deposit Contract",
        "owner": "Ethereum Foundation",
        "info": "Контракт стейкинга ETH 2.0. Более 13M ETH заблокировано для безопасности сети.",
        "significance": "important",
    },

    # ─── TON ──────────────────────────────────────────────────────
    "EQCD39VS5jcptHL8vMjEXrzGaRcCVYto7HUn4bpAOg8xqB2N": {
        "name": "💎 TON Foundation",
        "owner": "TON Foundation",
        "info": "Официальный кошелёк TON Foundation.",
        "significance": "important",
    },

    # ─── DOGECOIN ─────────────────────────────────────────────────
    "DH5yaie5oZN3X3Ww8UByVdFbYvqEoVcYjP": {
        "name": "🐕 Dogecoin Foundation",
        "owner": "Dogecoin Foundation",
        "info": "Официальный кошелёк Dogecoin Foundation.",
        "significance": "important",
    },

    # ─── TRON ─────────────────────────────────────────────────────
    "TN3W4H6rK2ce4vX9YnFQHwKENnHjoxb3m9": {
        "name": "🔗 TRON早期 кошелёк",
        "owner": "Ранняя экосистема TRON",
        "info": "Ранний кошелёк экосистемы TRON.",
        "significance": "historical",
    },
}


# ═══════════════════════════════════════════════════════════════════
#  ПАРСЕР
# ═══════════════════════════════════════════════════════════════════

class UniversalAddressParser:
    """
    Парсит адреса 20+ блокчейнов.
    Порядок важен — от наиболее специфичных к общим.
    Solana ПОСЛЕДНЯЯ — самый общий base58 паттерн.
    """

    # Каждый entry: (chain, subtype, regex, addr_type)
    # Порядок проверки — от самого специфичного к общему
    PATTERNS = [
        # ── BTC Bech32 (самый специфичный) ────────────────────────
        ("bitcoin", "taproot",  r"\bbc1p[a-zA-HJ-NP-Z0-9]{58}\b", "wallet"),
        ("bitcoin", "segwit",   r"\bbc1[a-zA-HJ-NP-Z0-9]{39,59}\b", "wallet"),
        ("bitcoin", "legacy",   r"\b1[a-km-zA-HJ-NP-Z1-9]{25,34}\b", "wallet"),
        # ⚠️ Waves (3P...) ДО Bitcoin P2SH (3...)!
        ("waves", "standard", r"\b3P[a-km-zA-HJ-NP-Z1-9]{32}\b", "wallet"),
        # ⚠️ BTC P2SH (3...) — ПОСЛЕ Waves (3P...)!
        ("bitcoin", "p2sh",     r"\b3[a-km-zA-HJ-NP-Z1-9]{25,34}\b", "wallet"),

        # ── ETH / EVM (0x... 40 hex) ─────────────────────────────
        ("ethereum", "standard", r"\b0x[a-fA-F0-9]{40}\b", "wallet_or_contract"),

        # ── TON ───────────────────────────────────────────────────
        ("ton", "user_friendly", r"\b(?:EQ|UQ)[A-Za-z0-9_\-]{44,50}\b", "wallet"),
        ("ton", "raw", r"\b-?\d+:[A-Fa-f0-9]{64}\b", "wallet"),

        # ── TRON ──────────────────────────────────────────────────
        ("tron", "standard", r"\bT[a-km-zA-HJ-NP-Z1-9]{33}\b", "wallet"),

        # ── DOGECOIN (D... 34 символа) — ДО Solana! ──────────────
        ("dogecoin", "standard", r"\bD[1-9A-HJ-NP-Za-km-z]{33}\b", "wallet"),

        # ── DASH (X... 34 символа) — ДО Solana! ──────────────────
        ("dash", "standard", r"\bX[1-9A-HJ-NP-Za-km-z]{33}\b", "wallet"),

        # ── ZCASH ─────────────────────────────────────────────────
        ("zcash", "shielded",  r"\bzs[a-km-zA-HJ-NP-Z1-9]{75}\b", "wallet"),
        ("zcash", "unified",   r"\bu1[a-z0-9]{100,}\b", "wallet"),
        ("zcash", "transparent", r"\bt1[a-km-zA-HJ-NP-Z1-9]{33}\b", "wallet"),

        # ── MONERO (4.../8... 95 символов) — длиннее Solana ──────
        ("monero", "standard", r"\b[48][A-Za-z0-9]{94}\b", "wallet"),

        # ── CARDANO ───────────────────────────────────────────────
        ("cardano", "shelley",  r"\baddr1[a-z0-9]{50,100}\b", "wallet"),
        ("cardano", "byron",    r"\bdb[a-z0-9]{50,100}\b", "wallet"),
        ("cardano", "enterprise", r"\baddr_test1[a-z0-9]{50,100}\b", "wallet"),

        # ── RAVENCOIN (R... uppercase!) — ПЕРЕД Ripple! ───────────
        ("ravencoin", "standard", r"\bR[1-9A-HJ-NP-Za-km-z]{32}\b", "wallet"),

        # ── RIPPLE / XRP (строго lowercase r!) ──────────────────────
        ("ripple", "standard", r"\br[1-9A-HJ-NP-Za-km-z]{32,34}\b", "wallet"),

        # ── LITECOIN (3 формата) ─────────────────────────────────
        ("litecoin", "bech32",  r"\bltc1[a-z0-9]{39,59}\b", "wallet"),
        ("litecoin", "legacy",  r"\bL[a-km-zA-HJ-NP-Z1-9]{26,33}\b", "wallet"),
        ("litecoin", "p2sh",    r"\bM[a-km-zA-HJ-NP-Z1-9]{26,33}\b", "wallet"),

        # ── STELLAR (G... 56 символов) ───────────────────────────
        ("stellar", "standard", r"\bG[A-Z2-7]{55}\b", "wallet"),

        # ── BNB BEACON (bnb1...) — ДО Solana! ────────────────────
        ("bnb_beacon", "standard", r"\bbnb1[a-z0-9]{37,42}\b", "wallet"),

        # ── COSMOS (cosmos1...) ──────────────────────────────────
        ("cosmos", "bech32", r"\bcosmos1[a-z0-9]{38,58}\b", "wallet"),

        # ── NEAR (...near) ───────────────────────────────────────
        ("near", "human", r"\b[a-z0-9_\-]{2,64}\.near\b", "wallet"),

        # ── TEZOS ─────────────────────────────────────────────────
        ("tezos", "tz1", r"\btz1[a-km-zA-HJ-NP-Z1-9]{33}\b", "wallet"),
        ("tezos", "tz2", r"\btz2[a-km-zA-HJ-NP-Z1-9]{33}\b", "wallet"),
        ("tezos", "tz3", r"\btz3[a-km-zA-HJ-NP-Z1-9]{33}\b", "wallet"),
        ("tezos", "kt1",  r"\bKT1[a-km-zA-HJ-NP-Z1-9]{33}\b", "contract"),

        # ── HEDERA (0.0.xxxx) ───────────────────────────────────
        ("hedera", "standard", r"\b0\.0\.\d{1,10}\b", "wallet"),

        # ── BITCOIN CASH ──────────────────────────────────────────
        ("bitcoincash", "standard", r"\bbitcoincash:q[a-z0-9]{41}\b", "wallet"),

        # ── ALGORAND (58 base32) ─────────────────────────────────
        ("algorand", "standard", r"\b[A-Z2-7]{58}\b", "wallet"),

        # ── SOLANA (последний — самый общий base58) ───────────────
        ("solana", "base58", r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", "wallet"),
    ]

    def parse(self, text: str) -> Optional[ParsedAddress]:
        """Парсит адрес из текста. Возвращает ParsedAddress или None."""
        text = text.strip()

        for chain, subtype, pattern, addr_type in self.PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                address = match.group(0)

                # Проверяем на исторический
                hist = HISTORICAL_ADDRESSES.get(address)

                return ParsedAddress(
                    address=address,
                    chain=chain,
                    address_type=addr_type,
                    format_subtype=subtype,
                    is_valid=True,
                    is_historical=hist is not None,
                    historical_info=hist or {},
                )

        return None

    def is_address(self, text: str) -> bool:
        """Быстрая проверка — является ли текст адресом"""
        return self.parse(text.strip()) is not None

    def get_chain(self, text: str) -> Optional[str]:
        """Возвращает chain или None"""
        parsed = self.parse(text.strip())
        return parsed.chain if parsed else None
