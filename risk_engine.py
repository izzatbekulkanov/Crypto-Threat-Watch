"""Risk Assessment Engine — Hamyon xavf darajasini baholash."""


def assess_risk(data: dict) -> tuple[str, str]:
    """Audit natijasiga asoslanib risk darajasini aniqlaydi.

    Mezonlar:
    - Juda yuqori hajm (volume) = yuqori risk
    - Ko'p tranzaksiyalar = o'rta risk
    - Kirim >> Chiqim yoki Chiqim >> Kirim = shubhali

    Args:
        data: API dan qaytgan audit natijasi.

    Returns:
        (risk_level, risk_emoji) tuple.
    """
    tx_count: int = data.get("grand_tx_count", data.get("tx_count", 0))
    tokens: list = data.get("tokens", [])
    assets: list = data.get("assets", [])

    # Volume ni raqamga aylantirish — TON tarmog'i uchun barcha aktivlar yig'indisi
    if assets:
        volume_num: float = sum(_parse_number(a.get("volume", "0")) for a in assets)
        income_num: float = sum(_parse_number(a.get("income", "0")) for a in assets)
        outcome_num: float = sum(_parse_number(a.get("outcome", "0")) for a in assets)
    else:
        volume_str: str = data.get("total_volume", "0")
        volume_num = _parse_number(volume_str)
        income_str: str = data.get("total_income", "0")
        outcome_str: str = data.get("total_outcome", "0")
        income_num = _parse_number(income_str)
        outcome_num = _parse_number(outcome_str)

    # Risk hisoblash
    risk_score: int = 0

    # 1. Hajm bo'yicha
    if volume_num > 100000:
        risk_score += 4
    elif volume_num > 10000:
        risk_score += 3
    elif volume_num > 1000:
        risk_score += 2
    elif volume_num > 100:
        risk_score += 1

    # 2. Tranzaksiyalar soni
    if tx_count > 500:
        risk_score += 3
    elif tx_count > 100:
        risk_score += 2
    elif tx_count > 50:
        risk_score += 1

    # 3. Kirim/Chiqim nomutanosibligi
    if income_num > 0 and outcome_num > 0:
        ratio: float = max(income_num, outcome_num) / min(income_num, outcome_num)
        if ratio > 10:
            risk_score += 3
        elif ratio > 5:
            risk_score += 2
        elif ratio > 3:
            risk_score += 1

    # 4. Ko'p turdagi tokenlar
    if len(tokens) > 10:
        risk_score += 2
    elif len(tokens) > 5:
        risk_score += 1

    # Risk darajasi
    if risk_score >= 8:
        return ("🔴 CRITICAL", "🔴")
    elif risk_score >= 5:
        return ("🟠 HIGH", "🟠")
    elif risk_score >= 3:
        return ("🟡 MEDIUM", "🟡")
    else:
        return ("🟢 LOW", "🟢")


def _parse_number(value: str) -> float:
    """Raqamli qiymatni stringdan ajratib olish."""
    try:
        # "1,250.50 USDT" -> 1250.50
        cleaned: str = ""
        for ch in value:
            if ch.isdigit() or ch == ".":
                cleaned += ch
            elif ch == "," :
                continue
            elif cleaned:
                break
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0
