"""
formatter.py — Красивое форматирование результатов скана для Telegram
"""


# ═══════════════════════════════════════════════════════════════════
#  ПЕРЕВОД ФЛАГОВ НА РУССКИЙ
# ═══════════════════════════════════════════════════════════════════

FLAG_TRANSLATIONS = {
    # RugCheck
    "Large Amount of LP Unlocked": (
        "Большая часть ликвидности НЕ заблокирована",
        "Создатель может вывести ликвидность в любой момент (rug pull)",
        "high"
    ),
    "Top 10 holders high ownership": (
        "Топ-10 холдеров владеют слишком большой долей",
        "Если продадут одновременно — цена обвалится",
        "medium"
    ),
    "Low Amount of holders": (
        "Очень мало холдеров",
        "Подозрительно низкая активность",
        "medium"
    ),
    "Mint authority enabled": (
        "Создатель может печатать новые токены",
        "Может обесценить твои токены, напечатав миллиарды новых",
        "high"
    ),
    "Freeze authority enabled": (
        "Создатель может заморозить токены",
        "Может заблокировать твои токены — ты не сможешь продать",
        "critical"
    ),
    "Single 100% LP Burned": (
        "Вся ликвидность сожжена",
        "Хороший знак — ликвидность заблокирована навсегда",
        "safe"
    ),
    # GoPlus
    "is_honeypot": (
        "Honeypot — нельзя продать",
        "Можно купить, но невозможно продать. Классический скам",
        "critical"
    ),
    "is_mintable": (
        "Можно печатать новые токены",
        "Владелец может напечатать бесконечно и обвалить цену",
        "high"
    ),
    "is_pausable": (
        "Торги можно остановить",
        "Владелец может заблокировать все транзакции",
        "high"
    ),
    "can_take_back_ownership": (
        "Владелец может вернуть контроль",
        "Даже после 'отказа от прав' может вернуть управление",
        "critical"
    ),
    "is_proxy": (
        "Прокси-контракт",
        "Код контракта можно изменить после деплоя",
        "high"
    ),
    "external_call": (
        "Внешние вызовы в контракте",
        "Контракт вызывает другие контракты — потенциальная уязвимость",
        "medium"
    ),
    "hidden_owner": (
        "Скрытый владелец",
        "Владелец скрыт в коде контракта",
        "high"
    ),
    "anti_whale": (
        "Ограничение на крупные сделки",
        "Можно ограничить продажу крупных держателей",
        "medium"
    ),
    "transfer_cooldown": (
        "Задержка между переводами",
        "Ограничение на частоту продаж",
        "medium"
    ),
    "trading_cooldown": (
        "Задержка между сделками",
        "Ограничение на частоту торговли",
        "medium"
    ),
}

SEVERITY_EMOJI = {
    "critical": "🚨",
    "high": "🔴",
    "medium": "🟠",
    "low": "🟡",
    "safe": "🟢",
    "unknown": "⚪",
}


def _translate_flag(flag_text: str) -> tuple[str, str, str]:
    """Переводит флаг на русский. Возвращает (ru_text, explanation, severity)"""
    # Точное совпадение
    if flag_text in FLAG_TRANSLATIONS:
        return FLAG_TRANSLATIONS[flag_text]
    # Частичное совпадение
    flag_lower = flag_text.lower()
    for key, val in FLAG_TRANSLATIONS.items():
        if key.lower() in flag_lower or flag_lower in key.lower():
            return val
    return (flag_text, "Требуется ручная проверка", "unknown")


def format_l1_report(l1_data: dict, wrapped_list: list[dict] | None = None) -> str:
    """
    Форматирует отчёт для L1 токена (CoinGecko + wrapped версии).
    l1_data: данные из coingecko.get_coin_data()
    wrapped_list: список wrapped версий из DexScreener
    """
    if not l1_data:
        return "❌ Данные по токену не найдены"

    symbol = l1_data.get("symbol", "?")
    name = l1_data.get("name", symbol)
    price = l1_data.get("price_usd") or 0
    mcap = l1_data.get("market_cap") or 0
    rank = l1_data.get("market_cap_rank") or "?"
    vol = l1_data.get("volume_24h") or 0
    pc24 = l1_data.get("price_change_24h") or 0
    pc7d = l1_data.get("price_change_7d") or 0
    pc30d = l1_data.get("price_change_30d") or 0
    ath = l1_data.get("ath") or 0
    ath_pct = l1_data.get("ath_change_percent") or 0
    supply = l1_data.get("circulating_supply") or 0
    max_supply = l1_data.get("max_supply") or 0

    def _fmt_price(p):
        if p >= 1:
            return f"${p:,.2f}"
        elif p >= 0.001:
            return f"${p:.4f}"
        else:
            return f"${p:.8f}"

    def _fmt_big(n):
        if not n:
            return "н/д"
        if n >= 1e12:
            return f"${n/1e12:.2f}T"
        elif n >= 1e9:
            return f"${n/1e9:.2f}B"
        elif n >= 1e6:
            return f"${n/1e6:.1f}M"
        elif n >= 1e3:
            return f"${n/1e3:.0f}K"
        return f"${n:,.0f}"

    def _fmt_supply(n):
        if not n:
            return "н/д"
        if n >= 1e9:
            return f"{n/1e9:.2f}B"
        elif n >= 1e6:
            return f"{n/1e6:.1f}M"
        elif n >= 1e3:
            return f"{n/1e3:.0f}K"
        return f"{n:,.0f}"

    def _pct_emoji(v):
        if v is None:
            return "⚪"
        return "🟢" if v >= 0 else "🔴"

    lines = []

    # ─── ЗАГОЛОВОК ──────────────────────────────────────────────
    lines.append(f"🟢 <b>НАСТОЯЩИЙ {symbol}</b> — {name}")
    lines.append(f"🛡 Trust: 100/100 | ✅ ПРОВЕРЕНО CoinGecko")
    lines.append(f"🏆 Ранг: #{rank}")
    lines.append("")

    # ─── ЦЕНА И ОСНОВНОЕ ────────────────────────────────────────
    lines.append(f"💰 <b>Цена:</b> {_fmt_price(price)}")
    lines.append(f"💎 <b>Market Cap:</b> {_fmt_big(mcap)}")
    lines.append(f"📈 <b>Объём 24ч:</b> {_fmt_big(vol)}")
    lines.append("")

    # ─── ДИНАМИКА ───────────────────────────────────────────────
    lines.append(f"📉 <b>Динамика:</b>")
    if pc24 is not None:
        lines.append(f"  • 24ч: {_pct_emoji(pc24)} {pc24:+.1f}%")
    if pc7d is not None:
        lines.append(f"  • 7д: {_pct_emoji(pc7d)} {pc7d:+.1f}%")
    if pc30d is not None:
        lines.append(f"  • 30д: {_pct_emoji(pc30d)} {pc30d:+.1f}%")
    lines.append("")

    # ─── ATH/ATL ────────────────────────────────────────────────
    if ath:
        lines.append(f"🏔 <b>ATH:</b> {_fmt_price(ath)} ({ath_pct:+.1f}% от текущей)")
    lines.append("")

    # ─── ЭМИССИЯ ────────────────────────────────────────────────
    if supply:
        supply_str = _fmt_supply(supply)
        if max_supply:
            supply_str += f" / {_fmt_supply(max_supply)}"
        lines.append(f"🪙 <b>Эмиссия:</b> {supply_str}")
        lines.append("")

    # ─── WRAPPED ВЕРСИИ ─────────────────────────────────────────
    if wrapped_list:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📦 <b>Wrapped-токены ({len(wrapped_list)})</b>")
        lines.append("")
        lines.append(f"Это токены {symbol} на других сетях (не на родной).")
        lines.append("Их можно использовать в DeFi-приложениях этой сети.")
        lines.append("")

        for i, w in enumerate(wrapped_list[:5], 1):
            w_chain = w.get("chain", "?")
            w_liq = float(w.get("liquidity") or 0)
            w_price = float(w.get("price_usd") or 0)
            w_sym = w.get("symbol", "?")

            liq_str = _fmt_big(w_liq) if w_liq else "н/д"
            price_str = _fmt_price(w_price) if w_price else "н/д"

            lines.append(f"  {i}️⃣ <b>{w_sym}</b> → сеть: {w_chain}")
            lines.append(f"     Цена: {price_str} | Ликвидность: {liq_str}")
            lines.append("")

        lines.append("⚠️ <b>Будь осторожен:</b> wrapped-токены бывают")
        lines.append("от проверенных эмитентов (Wormhole, Allbridge) и")
        lines.append("от левых проектов. Проверяй цену — если она")
        lines.append("отличается от оригинала более чем на 15%,")
        lines.append("это скорее всего скам-клон.")

    # ─── РЕКОМЕНДАЦИЯ ───────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <b>Где покупать:</b>")
    lines.append(f"• Оригинальный {symbol} → биржа (Bybit, OKX)")
    if wrapped_list:
        lines.append(f"• Wrapped → DEX на той сети (Uniswap, Raydium)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def format_telegram_message(result: dict, wrapped_warning: str = "") -> str:
    """
    Форматирует результат scan_token() в красивое Telegram-сообщение.
    Принимает dict с keys: success, metrics, assessment, scan_time_ms
    """
    a = result.get("assessment", {})
    m = result.get("metrics", {})

    risk = a.get("risk_level", "UNKNOWN").upper()
    score = a.get("score", 0)
    flags_count = a.get("red_flags_count", 0)

    # Risk emoji + CLEAR Russian label
    risk_map = {
        "SAFE":     ("🟢", "Риск скама: ОТСУТСТВУЕТ", "✅ Безопасно для входа"),
        "LOW":      ("🟢", "Риск скама: НИЗКИЙ", "✅ Можно рассматривать покупку"),
        "MEDIUM":   ("🟡", "Риск скама: СРЕДНИЙ", "⚠️ Будь осторожен — есть подозрительные признаки"),
        "HIGH":     ("🟠", "Риск скама: ВЫСОКИЙ", "🚨 Вероятность скама. Вход НЕ рекомендуется"),
        "CRITICAL": ("🔴", "Риск скама: КРИТИЧЕСКИЙ", "🚫 СКАМ! Не покупай этот токен!"),
    }
    risk_emoji, risk_label, risk_verdict = risk_map.get(risk, ("⚪", f"Риск скама: НЕИЗВЕСТЕН", "Недостаточно данных для оценки"))

    # Basic info
    address = m.get("address", "?")
    chain = m.get("chain", m.get("chain_id", "?"))
    price = m.get("price_usd", 0)
    liquidity = m.get("liquidity_usd", 0)
    volume = m.get("volume_24h", 0)
    holders = m.get("holder_count", 0)
    top10 = m.get("top10_holder_rate", 0)

    # NEW: extended metrics
    market_cap = m.get("market_cap", 0)
    fdv = m.get("fdv", 0)
    pc24 = m.get("price_change_24h", 0)
    pc6 = m.get("price_change_6h", 0)
    pc1 = m.get("price_change_1h", 0)
    buys = m.get("buys_24h", 0)
    sells = m.get("sells_24h", 0)
    created = m.get("pair_created_at", 0)
    lp_locked = m.get("lp_locked_rate", 0)
    is_open_source = m.get("is_open_source", False)

    # Format numbers
    def _fmt_price(p):
        if p >= 1:
            return f"${p:,.2f}"
        elif p >= 0.001:
            return f"${p:.6f}"
        elif p > 0:
            return f"${p:.10f}"
        return "$0"

    def _fmt_big(n):
        if not n:
            return "н/д"
        if n >= 1e9:
            return f"${n/1e9:.2f}B"
        elif n >= 1e6:
            return f"${n/1e6:.1f}M"
        elif n >= 1e3:
            return f"${n/1e3:.0f}K"
        return f"${n:,.0f}"

    def _pct_emoji(v):
        if v is None or v == 0:
            return "⚪"
        return "🟢" if v > 0 else "🔴"

    # Build report
    lines = []

    # Wrapped warning (top)
    if wrapped_warning:
        lines.append(f"⚠️ <b>ВНИМАНИЕ: {wrapped_warning}</b>")
        lines.append("")

    lines.append(f"{risk_emoji} <b>{risk_label}</b>")
    lines.append(f"📊 Оценка: {score}/100")
    lines.append(f"{risk_verdict}")
    lines.append(f"")
    lines.append(f"📍 <b>Адрес:</b> <code>{address[:20]}...</code>")
    if wrapped_warning:
        lines.append(f"🔗 <b>Сеть:</b> {chain} ⚠️ Wrapped")
        lines.append(f"💡 <i>Это обёртка. Оригинал торгуется на другой сети</i>")
    else:
        lines.append(f"🔗 <b>Сеть:</b> {chain}")
    lines.append(f"")

    # Price & Volume
    lines.append(f"💰 <b>Цена:</b> {_fmt_price(price)}")

    if market_cap:
        lines.append(f"💎 <b>Market Cap:</b> {_fmt_big(market_cap)}")
    lines.append(f"💧 <b>Ликвидность:</b> {_fmt_big(liquidity)}")
    lines.append(f"📈 <b>Объём 24ч:</b> {_fmt_big(volume)}")

    # Trades
    if buys or sells:
        total = buys + sells
        buy_pct = (buys / total * 100) if total else 0
        emoji = "🟢" if buy_pct > 55 else ("🔴" if buy_pct < 45 else "⚪")
        lines.append(f"🔄 <b>Сделки 24ч:</b> {emoji} {buys} buy / {sells} sell")
    else:
        lines.append(f"🔄 <b>Сделки 24ч:</b> н/д")

    if holders:
        lines.append(f"👥 <b>Холдеры:</b> {holders:,}")
    else:
        lines.append(f"👥 <b>Холдеры:</b> н/д")

    lines.append(f"")

    # Price changes
    has_changes = any(v for v in [pc24, pc6, pc1] if v is not None)
    if has_changes:
        lines.append(f"📉 <b>Динамика:</b>")
        if pc1 is not None:
            lines.append(f"  • 1ч: {_pct_emoji(pc1)} {pc1:+.1f}%")
        if pc6 is not None:
            lines.append(f"  • 6ч: {_pct_emoji(pc6)} {pc6:+.1f}%")
        if pc24 is not None:
            lines.append(f"  • 24ч: {_pct_emoji(pc24)} {pc24:+.1f}%")
        lines.append(f"")

    # Age
    if created:
        import time
        age_days = int((time.time() * 1000 - created) / 86400000)
        if age_days > 365:
            age_str = f"~{age_days // 365} г."
        elif age_days > 30:
            age_str = f"~{age_days // 30} мес."
        elif age_days > 0:
            age_str = f"~{age_days} дн."
        else:
            age_str = "менее дня"
        age_emoji = "🟢" if age_days > 90 else ("🟡" if age_days > 7 else "🔴")
        lines.append(f"📅 <b>Возраст:</b> {age_emoji} {age_str}")
        lines.append(f"")

    # Health
    health_lines = []
    if volume and market_cap:
        ratio = volume / market_cap * 100
        emoji = "✅" if 5 <= ratio <= 30 else "⚠️"
        health_lines.append(f"  • Vol/MCap: {ratio:.1f}% {emoji}")
    if liquidity and market_cap:
        ratio = liquidity / market_cap * 100
        emoji = "✅" if ratio >= 1 else "⚠️"
        health_lines.append(f"  • Liq/MCap: {ratio:.1f}% {emoji}")

    if health_lines:
        lines.append(f"📊 <b>Здоровье:</b>")
        lines.extend(health_lines)
        lines.append(f"")

    # Red flags
    critical_flags = a.get("critical_flags", 0)
    high_flags = a.get("high_flags", 0)
    flags = a.get("flags", [])
    safe_checks = a.get("safe_checks", [])

    if flags:
        lines.append(f"🚨 <b>Красные флаги ({flags_count}):</b>")
        if critical_flags:
            lines.append(f"  🔴 Критических: {critical_flags}")
        if high_flags:
            lines.append(f"  🟠 Высоких: {high_flags}")
        lines.append("")
        for f in flags[:5]:  # Ограничение длины
            ru_text, explanation, severity = _translate_flag(f)
            sev_emoji = SEVERITY_EMOJI.get(severity, "⚪")
            lines.append(f"  {sev_emoji} <b>{ru_text}</b>")
            lines.append(f"     └ {explanation}")
        lines.append(f"")

    # Safe checks
    if safe_checks:
        lines.append(f"✅ <b>Плюсы:</b>")
        for s in safe_checks[:5]:
            lines.append(f"  • ✅ {s}")
        lines.append(f"")

    # Scan time
    scan_time = result.get("scan_time_ms", 0)
    sources = result.get("sources", "DexScreener")
    lines.append(f"⏱ <i>Скан: {scan_time}ms | 📡 {sources}</i>")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# COMPARISON: /vs TOKEN1 TOKEN2
# ═══════════════════════════════════════════════════════════

def format_comparison(data_a: dict, data_b: dict) -> str:
    """Форматирует сравнение двух токенов."""
    def _sym(d):
        return d.get("symbol", d.get("baseToken", {}).get("symbol", "?"))

    def _name(d):
        return d.get("name", d.get("baseToken", {}).get("name", ""))

    def _price(d):
        p = d.get("price_usd", 0)
        return f"${p:.6f}" if p < 0.01 else f"${p:.2f}" if p < 1 else f"${p:,.2f}"

    def _liq(d):
        l = d.get("liquidity_usd", 0)
        if l >= 1_000_000:
            return f"${l/1_000_000:.1f}M"
        elif l >= 1_000:
            return f"${l/1_000:.0f}K"
        return f"${l:.0f}"

    def _vol(d):
        v = d.get("volume_24h", 0)
        if v >= 1_000_000:
            return f"${v/1_000_000:.1f}M"
        elif v >= 1_000:
            return f"${v/1_000:.0f}K"
        return f"${v:.0f}"

    def _mc(d):
        m = d.get("market_cap", d.get("fdv", 0))
        if m >= 1_000_000:
            return f"${m/1_000_000:.1f}M"
        elif m >= 1_000:
            return f"${m/1_000:.0f}K"
        return f"${m:.0f}"

    def _change(d, key="price_change_24h"):
        v = d.get(key, 0)
        emoji = "🟢" if v > 0 else "🔴" if v < 0 else "⚪"
        return f"{emoji} {v:+.1f}%"

    def _risk(d):
        risk = d.get("assessment", {}).get("risk_level", "unknown")
        emoji = {"safe": "🟢", "low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}.get(risk, "⚪")
        return f"{emoji} {risk.upper()}"

    sym_a, sym_b = _sym(data_a), _sym(data_b)

    lines = [
        f"⚔️ <b>СРАВНЕНИЕ: {sym_a} vs {sym_b}</b>",
        "",
        f"<b>{sym_a}</b> — {_name(data_a)}",
        f"<b>{sym_b}</b> — {_name(data_b)}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{'Параметр':<16} {sym_a:>10} {sym_b:>10}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 Цена          {_price(data_a):>10} {_price(data_b):>10}",
        f"💧 Ликвидность   {_liq(data_a):>10} {_liq(data_b):>10}",
        f"📊 Объём 24ч     {_vol(data_a):>10} {_vol(data_b):>10}",
        f"🏦 Market Cap    {_mc(data_a):>10} {_mc(data_b):>10}",
        f"📈 Изм. 24ч     {_change(data_a):>10} {_change(data_b):>10}",
        f"🛡 Риск         {_risk(data_a):>10} {_risk(data_b):>10}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Победитель по ликвидности
    liq_a = data_a.get("liquidity_usd", 0)
    liq_b = data_b.get("liquidity_usd", 0)
    if liq_a > liq_b * 1.5:
        lines.append(f"🏆 <b>{sym_a}</b> лидирует по ликвидности в {liq_a/max(liq_b,1):.1f}x")
    elif liq_b > liq_a * 1.5:
        lines.append(f"🏆 <b>{sym_b}</b> лидирует по ликвидности в {liq_b/max(liq_a,1):.1f}x")
    else:
        lines.append("🤝 Ликвидность примерно равна")

    # Флаги безопасности
    flags_a = data_a.get("assessment", {}).get("flags", [])
    flags_b = data_b.get("assessment", {}).get("flags", [])

    if flags_a or flags_b:
        lines.append("")
        lines.append("⚠️ <b>Риски:</b>")
        if flags_a:
            lines.append(f"  {sym_a}: {', '.join(flags_a[:3])}")
        if flags_b:
            lines.append(f"  {sym_b}: {', '.join(flags_b[:3])}")

    lines.append(f"\n⏱ <i>Данные: DexScreener + security APIs</i>")

    return "\n".join(lines)
