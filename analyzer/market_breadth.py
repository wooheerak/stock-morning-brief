"""
시장폭(Market Breadth) 엔진.

실시간 상승/하락 종목 수 데이터 없이,
아래 대리 지표(proxy)를 조합해 시장 폭을 수치화한다.

  - KOSPI / KOSDAQ 방향성 괴리 (대형주 vs 중소형주 대리)
  - KOSPI-KOSDAQ 등락률 괴리 폭
  - SOX-KOSDAQ 디커플링 (반도체 쏠림)
  - VIX 상승 여부
  - 달러/원 수준
  - 미국 지수 동조화 여부
  - 외국인 수급 방향 (있을 경우)

반환값
------
breadth_score : int 0~100   낮을수록 폭 좁음(대형주 쏠림)
risk_score    : int 0~100   높을수록 위험
breadth_label : str 넓음/보통/좁음/매우좁음
risk_label    : str 낮음/보통/높음/매우높음
factors       : list[str]   주요 요인 설명 (프롬프트·로그용)
divergence    : float       코스피-코스닥 등락률 차이 (절댓값)
"""
from __future__ import annotations
from typing import Dict, List


def compute_market_breadth(overseas: Dict, korean: Dict) -> Dict:
    """
    시장폭 점수 및 리스크 점수 산출.

    Parameters
    ----------
    overseas : fetch_overnight_summary() 반환값
    korean   : fetch_korean_index() 반환값

    Returns
    -------
    dict with keys: breadth_score, risk_score, breadth_label, risk_label,
                    factors, divergence
    """
    # ── 입력값 추출 ──────────────────────────────────────────────────────
    kospi_pct  = float(korean.get("코스피",  {}).get("change_pct", 0) or 0)
    kosdaq_pct = float(korean.get("코스닥",  {}).get("change_pct", 0) or 0)

    indices = overseas.get("indices", {})
    vix_pct  = float(indices.get("VIX(공포지수)",          {}).get("change_pct", 0) or 0)
    sox_pct  = float(indices.get("필라델피아반도체(SOX)", {}).get("change_pct", 0) or 0)
    sp500_pct = float(indices.get("S&P500",               {}).get("change_pct", 0) or 0)
    nasdaq_pct = float(indices.get("나스닥",               {}).get("change_pct", 0) or 0)

    fx = overseas.get("fx", {})
    usdkrw = float(fx.get("달러/원", {}).get("value", 0) or 0)

    investor = overseas.get("investor_trend", {})
    divergence = abs(kospi_pct - kosdaq_pct)

    # ── Breadth Score (기준 50) ───────────────────────────────────────────
    breadth = 50
    b_factors: List[str] = []

    # 1. KOSPI / KOSDAQ 방향성 (가장 큰 가중치)
    if kospi_pct > 0 and kosdaq_pct > 0:
        breadth += 12
        b_factors.append(f"코스피·코스닥 동반 상승 (+12)")
    elif kospi_pct > 0 and kosdaq_pct < 0:
        breadth -= 8
        b_factors.append(f"대형주 쏠림(코스피↑·코스닥↓) (-8)")
    elif kospi_pct < 0 and kosdaq_pct < 0:
        breadth -= 18
        b_factors.append(f"코스피·코스닥 동반 하락 (-18)")
    else:  # KOSPI ≤ 0, KOSDAQ > 0
        breadth -= 5
        b_factors.append(f"소형주 방어·대형주 약세 (-5)")

    # 2. 등락률 괴리 (위 방향성과 별개 패널티)
    if divergence >= 5:
        breadth -= 6
        b_factors.append(f"코스피/코스닥 괴리 {divergence:.1f}%p (-6)")
    elif divergence >= 3:
        breadth -= 3
        b_factors.append(f"코스피/코스닥 괴리 {divergence:.1f}%p (-3)")

    # 3. SOX-KOSDAQ 디커플링 (반도체만 오르고 코스닥 하락)
    if sox_pct >= 3 and kosdaq_pct <= -2:
        breadth -= 3
        b_factors.append(f"SOX {sox_pct:+.1f}%·코스닥 {kosdaq_pct:+.1f}% 디커플링 (-3)")

    # 4. VIX
    if vix_pct > 10:
        breadth -= 8
        b_factors.append(f"VIX {vix_pct:+.1f}% 급등 (-8)")
    elif vix_pct > 0:
        breadth -= 4
        b_factors.append(f"VIX {vix_pct:+.1f}% 상승 (-4)")

    # 5. 달러/원
    if usdkrw >= 1_500:
        breadth -= 4
        b_factors.append(f"달러/원 {usdkrw:,.0f}원 (-4)")
    elif usdkrw >= 1_450:
        breadth -= 2
        b_factors.append(f"달러/원 {usdkrw:,.0f}원 (-2)")

    # 6. 미국 지수 동조화 (소폭 가산)
    if sp500_pct > 0 and nasdaq_pct > 0 and kospi_pct > 0:
        breadth += 3
        b_factors.append(f"미국·코스피 동반 상승 (+3)")

    breadth = max(0, min(100, int(breadth)))

    # ── Risk Score (기준 20) ─────────────────────────────────────────────
    risk = 20
    r_factors: List[str] = []

    if vix_pct > 10:
        risk += 18
        r_factors.append(f"VIX {vix_pct:+.1f}% 급등 (+18)")
    elif vix_pct > 0:
        risk += 10
        r_factors.append(f"VIX {vix_pct:+.1f}% 상승 (+10)")

    if usdkrw >= 1_500:
        risk += 15
        r_factors.append(f"달러/원 {usdkrw:,.0f}원 (+15)")
    elif usdkrw >= 1_450:
        risk += 8
        r_factors.append(f"달러/원 {usdkrw:,.0f}원 (+8)")

    if kosdaq_pct <= -2:
        risk += 12
        r_factors.append(f"코스닥 {kosdaq_pct:+.1f}% 급락 (+12)")
    elif kosdaq_pct <= -1:
        risk += 6
        r_factors.append(f"코스닥 {kosdaq_pct:+.1f}% 하락 (+6)")

    if divergence >= 5:
        risk += 10
        r_factors.append(f"코스피/코스닥 괴리 {divergence:.1f}%p (+10)")
    elif divergence >= 3:
        risk += 5
        r_factors.append(f"코스피/코스닥 괴리 {divergence:.1f}%p (+5)")

    if sox_pct >= 5 and kosdaq_pct <= 0:
        risk += 8
        r_factors.append(f"SOX {sox_pct:+.1f}% 대비 코스닥 부진 (+8)")

    # 외국인 순매도 (데이터 있을 경우)
    kospi_inv = investor.get("코스피", {})
    if isinstance(kospi_inv, dict):
        f_val = kospi_inv.get("foreigner", 0)
        if f_val < -3_000:
            risk += 12
            r_factors.append(f"외국인 {f_val:+,d}억 순매도 (+12)")
        elif f_val < -1_000:
            risk += 6
            r_factors.append(f"외국인 {f_val:+,d}억 순매도 (+6)")

    risk = max(0, min(100, int(risk)))

    # ── 레이블 ───────────────────────────────────────────────────────────
    if breadth >= 65:
        breadth_label = "넓음"
    elif breadth >= 45:
        breadth_label = "보통"
    elif breadth >= 25:
        breadth_label = "좁음"
    else:
        breadth_label = "매우좁음"

    if risk >= 70:
        risk_label = "매우높음"
    elif risk >= 50:
        risk_label = "높음"
    elif risk >= 30:
        risk_label = "보통"
    else:
        risk_label = "낮음"

    return {
        "breadth_score":  breadth,
        "risk_score":     risk,
        "breadth_label":  breadth_label,
        "risk_label":     risk_label,
        "factors":        b_factors + r_factors,
        "b_factors":      b_factors,
        "r_factors":      r_factors,
        "divergence":     round(divergence, 2),
        "kospi_pct":      round(kospi_pct, 2),
        "kosdaq_pct":     round(kosdaq_pct, 2),
    }


def format_breadth_for_prompt(info: Dict) -> str:
    """
    Gemini 프롬프트 삽입용 문자열 생성.
    """
    bs = info.get("breadth_score", 50)
    bl = info.get("breadth_label", "보통")
    rs = info.get("risk_score", 30)
    rl = info.get("risk_label", "보통")
    b_factors = info.get("b_factors", [])
    r_factors = info.get("r_factors", [])
    div = info.get("divergence", 0)

    factor_str = "\n".join(f"  - {f}" for f in (b_factors + r_factors)) or "  - 요인 없음"

    # 섹터 가이드라인 (breadth 수준별 조건부)
    sector_guide = ""
    if bs < 25:
        sector_guide = (
            "⚠️ [매우좁음] strong_sectors: 실제 상승 대형 섹터 1~2개만 허용. "
            "KOSDAQ 비중 높은 섹터(바이오·중소형성장·게임 등)는 strong_sectors 포함 금지, "
            "weak_sectors에 추가 검토."
        )
    elif bs < 40:
        sector_guide = (
            "⚠️ [좁음] KOSDAQ 비중 높은 섹터(바이오·게임·중소형성장)를 strong_sectors에 포함하지 말 것. "
            f"코스닥 {info.get('kosdaq_pct', 0):+.1f}% 음수 시 해당 섹터는 weak_sectors 후보."
        )

    lines = [
        f"시장폭 점수: {bs}/100 ({bl})  |  리스크 점수: {rs}/100 ({rl})",
        f"코스피-코스닥 괴리: {div:.1f}%p",
        "주요 요인:",
        factor_str,
    ]
    if sector_guide:
        lines.append(sector_guide)

    return "\n".join(lines)
