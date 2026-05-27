"""
시장 데이터 검증 레이어.
각 지표의 정상 범위를 체크하고 이상 시 경고 / 치명 오류를 반환한다.
"""
from typing import Dict, List, Tuple

# (하한, 상한) — 파싱 오류를 잡기 위한 넓은 범위
_RANGES: Dict[str, Tuple[float, float]] = {
    # 해외 지수
    "나스닥":               (5_000,  80_000),
    "S&P500":              (1_000,  20_000),
    "다우존스":             (10_000, 120_000),
    "필라델피아반도체(SOX)": (500,    30_000),
    "VIX(공포지수)":        (5,      150),
    # 미국 주요 종목
    "엔비디아":             (10,     10_000),
    "테슬라":               (10,     5_000),
    "애플":                 (50,     1_500),
    "마이크로소프트":       (50,     2_000),
    # 환율
    "달러/원":              (800,    2_500),
    "달러/엔":              (50,     250),
    # 채권 금리 (%)
    "미국채10년물":         (0.1,    20),
    # 국내 지수
    "코스피":               (500,    20_000),
    "코스닥":               (300,    5_000),
}

# 단일 세션 변동률 임계값 (이 이상이면 파싱 오류 의심)
_MAX_CHANGE_PCT = 25.0

# 치명적 오류로 판단할 핵심 지표 (이상 시 브리핑 중단)
_CRITICAL_ITEMS = {"나스닥", "S&P500", "달러/원", "코스피", "코스닥"}


def _check_item(name: str, d: Dict, warnings: List[str]) -> bool:
    """단일 항목 검증. 치명 오류면 False 반환."""
    if not d:
        warnings.append(f"⚠️  {name}: 수집 실패 (빈 데이터)")
        return False

    val = d.get("value", 0)

    # 값 범위 체크
    rng = _RANGES.get(name)
    if rng and not (rng[0] <= val <= rng[1]):
        warnings.append(
            f"🚨 {name}: 비정상 값 {val:,.2f}"
            f"  (정상 범위 {rng[0]:,} ~ {rng[1]:,}) — 파싱 오류 의심"
        )
        return False

    # 변동률 이상치 (경고만, 치명 X)
    change_pct = abs(d.get("change_pct", 0))
    if change_pct > _MAX_CHANGE_PCT:
        warnings.append(
            f"⚠️  {name}: 단일 세션 변동률 {change_pct:.1f}%"
            f" — {_MAX_CHANGE_PCT}% 초과, 수치 확인 필요"
        )

    return True


def validate_market_data(overseas: Dict, korean: Dict) -> Tuple[bool, List[str]]:
    """
    해외 + 국내 시장 데이터 전체 검증.

    Returns:
        (critical_error, warnings)
        critical_error=True  → 핵심 데이터 이상, 브리핑 중단 권고
        critical_error=False → 경고만 있거나 정상
    """
    warnings: List[str] = []
    critical = False

    def _flag(name: str, d: Dict) -> None:
        nonlocal critical
        ok = _check_item(name, d, warnings)
        if not ok and name in _CRITICAL_ITEMS:
            critical = True

    for name, d in overseas.get("indices", {}).items():
        _flag(name, d)

    for name, d in overseas.get("stocks", {}).items():
        _flag(name, d)

    for name, d in overseas.get("fx", {}).items():
        _flag(name, d)

    for name, d in overseas.get("bonds", {}).items():
        _flag(name, d)

    for name, d in korean.items():
        if name.startswith("_"):   # _fetched_at, _is_intraday 등 메타 키 skip
            continue
        _flag(name, d)

    return critical, warnings
