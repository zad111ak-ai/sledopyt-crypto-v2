"""
semantic.py — Семантический парсер: понимание смысла без нейросетей
3 техники: синонимы + fuzzy matching + иерархические правила
"""
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ═══════════════════════════════════════════════════════════════════
#  СЛОВАРЬ ИНТЕНТОВ С СИНОНИМАМИ
# ═══════════════════════════════════════════════════════════════════

INTENTS = {
    "EXIT_STRATEGY": {
        "description": "Когда и как выходить из позиции",
        "priority": 10,
        "triggers": [
            "когда выходить", "когда продать", "когда фиксировать",
            "стратегия выхода", "план выхода", "exit strategy",
            "when to sell", "when to exit", "take profit",
            "выйти из", "продать", "зафиксировать прибыль",
            "слить", "закрыть позицию", "выход",
            "пора продавать", "стоит ли продавать",
            "как выйти в плюс", "на каком уровне продавать",
        ],
        "synonyms": {
            "выход": ["sell", "exit", "продать", "закрыть", "фикс"],
            "когда": ["в какой момент", "при какой цене", "на каком уровне", "when"],
            "стратегия": ["план", "алгоритм", "strategy", "plan"],
        },
        "required_entities": ["token"],
    },
    "BUY_DECISION": {
        "description": "Стоит ли покупать токен",
        "priority": 10,
        "triggers": [
            "стоит ли покупать", "можно ли брать", "заходить ли",
            "buy or not", "should i buy", "стоит ли заходить",
            "покупать или нет", "есть ли смысл покупать",
            "хорошая ли идея", "перспектива токена",
        ],
        "synonyms": {
            "покупать": ["buy", "брать", "заходить", "инвестировать", "вкладываться"],
            "стоит": ["есть смысл", "имеет смысл", "should", "worth"],
        },
        "required_entities": ["token"],
    },
    "TOKEN_ANALYSIS": {
        "description": "Полный анализ токена",
        "priority": 8,
        "triggers": [
            "проверь токен", "анализ токена", "что с токеном",
            "check token", "analyze", "расскажи про",
            "что это за токен", "инфа по токену", "аудит",
            "проверь", "чек", "check", "анализ", "аудит токена",
            "узнать про", "что за", "tell me about", "what is",
            "how is", "как дела с", "что происходит",
        ],
        "synonyms": {
            "проверь": ["анализ", "check", "analyze", "аудит", "разбор"],
            "токен": ["монета", "коин", "token", "coin", "актив"],
        },
        "required_entities": ["token"],
    },
    "WHALE_ACTIVITY": {
        "description": "Кто покупает/продает токен",
        "priority": 9,
        "triggers": [
            "кто покупает", "кто продает", "киты в токене",
            "whale activity", "smart money", "кто заходит",
            "крупные игроки", "инсайдеры", "insiders",
        ],
        "synonyms": {
            "киты": ["whales", "smart money", "крупные игроки", "инсайдеры"],
            "покупает": ["заходит", "набирает", "accumulates", "buys"],
        },
        "required_entities": ["token"],
    },
    "RUG_CHECK": {
        "description": "Проверка на скам/rug pull",
        "priority": 10,
        "triggers": [
            "скам ли", "безопасен ли", "не развод ли",
            "is it safe", "rug pull check", "можно ли доверять",
            "честный ли", "не кинут ли", "honeypot",
            "скам?", "safe?", "legit?",
        ],
        "synonyms": {
            "скам": ["scam", "развод", "обман", "кидалово", "rug"],
            "безопасен": ["safe", "честный", "надежный", "legit"],
        },
        "required_entities": ["token"],
    },
    "WALLET_DNA": {
        "description": "Анализ кошелька",
        "priority": 9,
        "triggers": [
            "проверь кошелек", "dna кошелька", "кто владелец",
            "wallet dna", "analyze wallet", "анализ адреса",
        ],
        "synonyms": {
            "кошелек": ["wallet", "адрес", "address", "кошель"],
        },
        "required_entities": ["wallet"],
    },
    "SHOW_BALANCE": {
        "description": "Показать баланс",
        "priority": 6,
        "triggers": [
            "баланс", "мой баланс", "сколько кредитов",
            "balance", "my credits", "кредиты",
        ],
        "synonyms": {},
        "required_entities": [],
    },
    "DEPOSIT": {
        "description": "Пополнить баланс",
        "priority": 6,
        "triggers": [
            "пополнить", "купить кредиты", "оплатить",
            "deposit", "buy credits", "top up",
        ],
        "synonyms": {},
        "required_entities": [],
    },
    "HELP": {
        "description": "Помощь",
        "priority": 5,
        "triggers": [
            "помощь", "как пользоваться", "что умеешь",
            "help", "how to", "guide",
        ],
        "synonyms": {},
        "required_entities": [],
    },
    "GREETING": {
        "description": "Приветствие",
        "priority": 4,
        "triggers": [
            "привет", "здарова", "hi", "hello", "ку",
            "добрый день", "good morning", "hey",
        ],
        "synonyms": {},
        "required_entities": [],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  РЕЗУЛЬТАТ ПАРСИНГА
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SemanticResult:
    intent: str
    confidence: float
    entities: Dict = field(default_factory=dict)
    raw_text: str = ""
    matched_phrases: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
#  СЕМАНТИЧЕСКИЙ ПАРСЕР
# ═══════════════════════════════════════════════════════════════════

class SemanticParser:
    """
    Понимает смысл запросов без нейросетей.
    3 техники: синонимы + fuzzy matching + иерархия.
    """

    def __init__(self):
        self.fuzzy_threshold = 0.65

    def parse(self, text: str) -> SemanticResult:
        """Главный метод — анализирует текст и возвращает интент."""
        text_lower = text.lower().strip()

        # 1. Извлекаем сущности (адреса, тикеры, URL)
        entities = self._extract_entities(text)

        # 2. Сопоставляем с интентами
        candidates = []
        for intent_name, intent_data in INTENTS.items():
            score, matched = self._match_intent(text_lower, intent_data)
            if score > 0.25:
                candidates.append({
                    "intent": intent_name,
                    "score": score,
                    "matched": matched,
                    "priority": intent_data.get("priority", 5),
                    "required_entities": intent_data.get("required_entities", []),
                })

        # 3. Сортируем: приоритет × уверенность
        candidates.sort(key=lambda x: x["priority"] * x["score"], reverse=True)

        # 4. Выбираем лучший с проверкой required_entities
        #    "token" в required → проверяем token_symbol ИЛИ token_address
        best = None
        for c in candidates:
            required = c["required_entities"]
            if not required:
                best = c
                break
            ok = False
            for r in required:
                if r == "token":
                    if "token_symbol" in entities or "token_address" in entities:
                        ok = True
                        break
                elif r == "wallet":
                    if "wallet" in entities:
                        ok = True
                        break
                elif r in entities:
                    ok = True
                    break
            if ok:
                best = c
                break

        if not best:
            # Fallback: если есть адрес — SCAN, иначе UNKNOWN
            if "token_address" in entities:
                return SemanticResult("SCAN", 1.0, entities, text)
            if "token_symbol" in entities:
                return SemanticResult("TOKEN_ANALYSIS", 0.5, entities, text)
            return SemanticResult("UNKNOWN", 0.0, entities, text)

        return SemanticResult(
            intent=best["intent"],
            confidence=best["score"],
            entities=entities,
            raw_text=text,
            matched_phrases=best["matched"],
        )

    def _match_intent(self, text: str, intent_data: Dict) -> Tuple[float, List[str]]:
        """Сопоставляет текст с интентом через 3 уровня."""
        text_words = set(text.split())
        matched: List[str] = []
        max_score = 0.0

        # ── Уровень 1: Exact match (точные фразы) ──────
        for trigger in intent_data["triggers"]:
            if trigger.lower() in text:
                matched.append(trigger)
                score = min(1.0, 0.5 + len(trigger.split()) * 0.1)
                max_score = max(max_score, score)

        # ── Уровень 2: Synonym match ────────────────────
        for key_word, synonyms in intent_data.get("synonyms", {}).items():
            for syn in synonyms + [key_word]:
                if syn.lower() in text_words:
                    ctx = self._check_context(text, intent_data, syn.lower())
                    if ctx > 0:
                        matched.append(syn)
                        max_score = max(max_score, ctx * 0.8)

        # ── Уровень 3: Fuzzy match (нечёткий) ───────────
        if max_score < 0.5:
            for trigger in intent_data["triggers"]:
                fs = self._fuzzy_match(text, trigger.lower())
                if fs > self.fuzzy_threshold:
                    matched.append(f"~{trigger}")
                    max_score = max(max_score, fs * 0.7)

        return max_score, matched

    def _check_context(self, text: str, intent_data: Dict, found_word: str) -> float:
        """Проверяет контекст — есть ли рядом другие слова интента."""
        text_words = set(text.split())
        score = 0.4
        for key_word, synonyms in intent_data.get("synonyms", {}).items():
            for w in synonyms + [key_word]:
                if w.lower() in text_words and w.lower() != found_word:
                    score += 0.2
        return min(1.0, score)

    def _fuzzy_match(self, text: str, pattern: str) -> float:
        """Нечёткое сравнение строк (SequenceMatcher)."""
        text_words = text.split()
        pattern_words = pattern.split()
        if not pattern_words:
            return 0.0
        total = 0.0
        for pw in pattern_words:
            best = max(
                (SequenceMatcher(None, pw, tw).ratio() for tw in text_words),
                default=0.0,
            )
            total += best
        return total / len(pattern_words)

    def _extract_entities(self, text: str) -> Dict:
        """Извлекает сущности: адреса, тикеры, URL."""
        entities = {}

        # ─── АДРЕСА КРИПТОВАЛЮТ ──────────────────────────────────

        # ETH / BSC / Polygon / Arbitrum / Base / Optimism (0x...)
        m = re.search(r'0x[a-fA-F0-9]{40}', text)
        if m:
            entities["wallet"] = m.group(0)
            entities["token_address"] = m.group(0)

        # Bitcoin legacy P2PKH (1...)
        m = re.search(r'\b(1[a-km-zA-HJ-NP-Z1-9]{25,34})\b', text)
        if m and "wallet" not in entities:
            entities["wallet"] = m.group(0)
            entities["token_address"] = m.group(0)
            entities["chain_hint"] = "bitcoin"

        # Bitcoin P2SH (3...)
        m = re.search(r'\b(3[a-km-zA-HJ-NP-Z1-9]{25,34})\b', text)
        if m and "wallet" not in entities:
            entities["wallet"] = m.group(0)
            entities["token_address"] = m.group(0)
            entities["chain_hint"] = "bitcoin"

        # Bitcoin bech32 (bc1...)
        m = re.search(r'\bbc1[a-zA-HJ-NP-Z0-9]{25,90}\b', text)
        if m and "wallet" not in entities:
            entities["wallet"] = m.group(0)
            entities["token_address"] = m.group(0)
            entities["chain_hint"] = "bitcoin"

        # TON (EQ... or UQ..., 46-50 chars после префикса)
        m = re.search(r'(?:EQ|UQ)[A-Za-z0-9_\-]{44,50}', text)
        if m and "wallet" not in entities:
            entities["wallet"] = m.group(0)
            entities["token_address"] = m.group(0)
            entities["chain_hint"] = "ton"

        # Tron (T..., 34 chars)
        m = re.search(r'\bT[a-zA-HJ-NP-Z1-9]{33}\b', text)
        if m and "wallet" not in entities:
            entities["wallet"] = m.group(0)
            entities["token_address"] = m.group(0)
            entities["chain_hint"] = "tron"

        # Solana (base58, 32-44 chars — без 0/O/I/l)
        m = re.search(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b', text)
        if m and "wallet" not in entities:
            addr = m.group(0)
            # Исключаем BTC-адресы (уже проверены выше) и слишком короткие
            if len(addr) >= 32 and not addr.startswith(('1', '3', 'T')):
                entities["wallet"] = addr
                entities["token_address"] = addr
                entities["chain_hint"] = "solana"

        # ─── ТИКЕРЫ ──────────────────────────────────────────────

        # Тикер с $ ($PEPE)
        m = re.search(r'\$([A-Z]{2,10})\b', text.upper())
        if m:
            entities["token_symbol"] = m.group(1)
        else:
            # Заглавные слова (PEPE, HAMSTER)
            skip = {"THE", "AND", "FOR", "WITH", "FROM", "WHEN", "HOW", "WHAT", "THIS", "THAT"}
            for w in re.findall(r'\b([A-Z][A-Z0-9]{2,9})\b', text):
                if w not in skip:
                    entities["token_symbol"] = w
                    break

        # Fallback 1: слово с заглавной (Gram, Bitcoin, Pepe)
        if "token_symbol" not in entities:
            skip_lower = {"the", "and", "for", "with", "from", "when", "how", "what", "this", "that",
                          "проверь", "скам", "купить", "продать", "привет", "помощь", "баланс"}
            for w in text.split():
                wl = w.lower().strip(".,!?;:")
                if len(wl) >= 2 and wl.isalpha() and wl not in skip_lower and w[0].isupper():
                    entities["token_symbol"] = wl.upper()
                    break

        # Fallback 2: последнее слово после предлогов «про/о/об/about»
        if "token_symbol" not in entities:
            m = re.search(r'(?:про|о|об|about)\s+(\w+)', text.lower())
            if m:
                word = m.group(1).strip(".,!?;:")
                if len(word) >= 2:
                    entities["token_symbol"] = word.upper()

        # Fallback 3: одно короткое слово = скорее всего тикер
        if "token_symbol" not in entities:
            words = text.split()
            if len(words) == 1 and len(words[0]) <= 20 and words[0].isalpha():
                entities["token_symbol"] = words[0].upper()

        # URL
        m = re.search(r'https?://\S+', text)
        if m:
            url = m.group(0)
            if any(d in url for d in ["dexscreener", "dedust", "ston.fi", "uniswap"]):
                entities["dex_url"] = url

        # Сумма
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(usd|usdt|ton|rub|\$)?', text.lower())
        if m:
            entities["amount"] = float(m.group(1).replace(',', '.'))

        return entities
