"""
PNG-генератор для шеринга отчётов в Twitter.
Dark theme, 1200x675, без внешних зависимостей.
"""
import io
from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int, bold: bool = False):
    """Загружает шрифт, fallback на дефолтный."""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _risk_color(score: int) -> str:
    if score >= 80:
        return "#00FF88"
    elif score >= 60:
        return "#FFD700"
    elif score >= 40:
        return "#FF8C00"
    else:
        return "#FF4444"


def generate_report_card(token_data: dict, security: dict) -> bytes:
    """
    PNG 1200x675 для Twitter/Telegram.

    token_data: {"symbol", "name", "chain", "price", "market_cap", "liquidity", "holders"}
    security: {"score": 0-100, "flags": [...], "risk_level": "low|medium|high|critical"}
    """
    W, H = 1200, 675
    BG = "#0D1117"
    HEADER = "#1A1F2E"
    TEXT_W = "#FFFFFF"
    TEXT_G = "#AAAAAA"
    TEXT_D = "#666666"

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    font_big = _get_font(48, bold=True)
    font_med = _get_font(28, bold=True)
    font_small = _get_font(20)
    font_tiny = _get_font(16)

    score = security.get("score", 0)
    color = _risk_color(score)

    # ─── Header ───────────────────────────────────────────────
    draw.rectangle([0, 0, W, 180], fill=HEADER)
    symbol = f"${token_data.get('symbol', 'TOKEN')}"
    name = token_data.get("name", "")[:40]
    chain = token_data.get("chain", "").upper()

    draw.text((50, 40), symbol, font=font_big, fill=TEXT_W)
    draw.text((50, 100), name, font=font_small, fill=TEXT_G)
    draw.text((50, 130), chain, font=font_tiny, fill=TEXT_D)

    # Score circle
    cx, cy, r = 1050, 90, 60
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BG, outline=color, width=4)
    # Center the score text
    score_text = str(score)
    draw.text((cx - 18, cy - 22), score_text, font=font_med, fill=color)
    draw.text((cx - 15, cy + 18), "/100", font=font_tiny, fill="#888888")

    # ─── Metrics cards ────────────────────────────────────────
    metrics = [
        ("Price", f"${token_data.get('price', 0):.6f}"),
        ("Mkt Cap", f"${token_data.get('market_cap', 0) / 1e6:.1f}M"),
        ("Liquidity", f"${token_data.get('liquidity', 0) / 1e3:.0f}K"),
        ("Holders", f"{token_data.get('holders', 0):,}"),
    ]

    for i, (label, value) in enumerate(metrics):
        x = 50 + i * 280
        draw.rounded_rectangle([x, 220, x + 260, 330], radius=8, fill=HEADER)
        draw.text((x + 15, 235), label, font=font_tiny, fill="#888888")
        draw.text((x + 15, 270), value, font=font_med, fill=TEXT_W)

    # ─── Security flags ───────────────────────────────────────
    draw.text((50, 380), "Security:", font=font_med, fill=TEXT_W)
    y = 420
    flags = security.get("flags", [])[:4]
    if flags:
        for flag in flags:
            draw.text((70, y), f"• {flag[:60]}", font=font_small, fill="#CCCCCC")
            y += 28
    else:
        draw.text((70, y), "No red flags detected", font=font_small, fill="#00FF88")

    # ─── Risk badge ───────────────────────────────────────────
    risk = security.get("risk_level", "unknown").upper()
    draw.rounded_rectangle([50, y + 20, 250, y + 60], radius=6, fill=color)
    draw.text((65, y + 26), f"Risk: {risk}", font=font_small, fill="#0D1117")

    # ─── Footer ───────────────────────────────────────────────
    draw.rectangle([0, H - 60, W, H], fill=HEADER)
    draw.text((50, H - 45), "@Cryptop_q_bot • Крипто_следопыт", font=font_small, fill=TEXT_D)
    draw.text((W - 300, H - 45), "🛡 Detective Report", font=font_small, fill="#444444")

    # ─── Save ─────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
