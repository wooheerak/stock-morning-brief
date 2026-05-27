"""
전략 가드레일 — AI 분석 결과를 시장 데이터로 후처리 보정.

AI가 반환한 strategy_stance 를 시장 조건이 맞지 않을 때 강제 하향한다.
승격(하향된 전략을 높이는 것)은 금지 — 가드레일은 보수적 방향으로만 작동한다.
"""
from __future__ import annotations

from typing import Dict, List, Tuple


# ── 스탠스 레벨 정의 (높을수록 공격적) ──────────────────────────────────
_LEVELS = {"적극매수": 3, "보수적매수": 2, "관망": 1, "위험관리": 0}
_EMOJI  = {"적극매수": "🟢", "보수적매수": "🟡", "관망": "🟡", "위험관리": "🔴"}
_CASH   = {
    "적극매수":  "10~20%",
    "보수적매수": "30~40%",
    "관망":      "50~60%",
    "위험관리":  "70% 이상",
}


def _check_rules(
    kospi_pct: float,
    kosdaq_pct: float,
    vix_pct: float,
    usdkrw_val: float,
    score: int,
) -> List[Tuple[str, str]]:
    """각 규칙 위반 여부 확인 → [(target_label, reason_str)] 반환."""
    hits: List[Tuple[str, str]] = []

    # R1: 코스피 3%+ 강세인데 코스닥 2%- 약세 → 대형주 쏠림, 시장 폭 좁음
    if kospi_pct >= 3 and kosdaq_pct <= -2:
        hits.append((
            "보수적매수",
            f"코스피 {kospi_pct:+.1f}% vs 코스닥 {kosdaq_pct:+.1f}% — 대형주 쏠림"
        ))

    # R2: VIX 상승 + 환율 1,500원 이상 → 리스크 지표 경계
    if vix_pct > 0 and usdkrw_val >= 1_500:
        hits.append((
            "관망",
            f"VIX {vix_pct:+.1f}% + 달러/원 {usdkrw_val:,.0f}원"
        ))

    # R3: R1 + VIX 동시 → 관망 강제
    if kospi_pct >= 3 and kosdaq_pct <= -2 and vix_pct > 0:
        hits.append((
            "관망",
            "코스피/코스닥 쏠림 + VIX 동시 상승"
        ))

    # R4: 심리점수 < 45 인데 적극매수 금지
    if score < 45:
        hits.append((
            "보수적매수",
            f"심리점수 {score}점 < 45"
        ))

    # R5: 심리점수 < 35 → 최소 관망
    if score < 35:
        hits.append((
            "관망",
            f"심리점수 {score}점 < 35 — 관망 강제"
        ))

    return hits


def apply_strategy_guardrails(
    analysis: Dict,
    overseas: Dict,
    korean: Dict,
) -> Dict:
    """
    AI 분석 후처리: 시장 조건에 따른 전략 스탠스 강제 하향.

    Parameters
    ----------
    analysis : dict   analyze_morning_brief() 반환값 (dict)
    overseas : dict   fetch_overnight_summary() 반환값
    korean   : dict   fetch_korean_index() 반환값

    Returns
    -------
    보정된 analysis dict
    """
    # ── 입력값 추출 ──────────────────────────────────────────────────────
    kospi_pct  = float(korean.get("코스피", {}).get("change_pct", 0) or 0)
    kosdaq_pct = float(korean.get("코스닥", {}).get("change_pct", 0) or 0)
    vix_pct    = float(
        overseas.get("indices", {}).get("VIX(공포지수)", {}).get("change_pct", 0) or 0
    )
    usdkrw_val = float(
        overseas.get("fx", {}).get("달러/원", {}).get("value", 0) or 0
    )
    score         = int(analysis.get("sentiment_score", 50))
    current_label = analysis.get("strategy_stance", {}).get("label", "관망")
    current_level = _LEVELS.get(current_label, 1)

    # ── 규칙 평가 ──────────────────────────────────────────────────────────
    hits = _check_rules(kospi_pct, kosdaq_pct, vix_pct, usdkrw_val, score)

    # 가장 낮은(보수적) 타겟 레벨 선택
    target_label  = current_label
    target_level  = current_level
    active_reasons: List[str] = []

    for label, reason in hits:
        lv = _LEVELS.get(label, 1)
        if lv < target_level:
            target_label = label
            target_level = lv
            active_reasons = [reason]
        elif lv == target_level and reason not in active_reasons:
            active_reasons.append(reason)

    # ── 하향 적용 (승격 없음) ─────────────────────────────────────────────
    guardrail_applied = False
    if target_level < current_level and target_label != current_label:
        reason_str = " | ".join(active_reasons)
        analysis["strategy_stance"] = {
            "label":      target_label,
            "emoji":      _EMOJI[target_label],
            "cash_ratio": _CASH[target_label],
        }
        original_strategy = analysis.get("today_strategy", "")
        analysis["today_strategy"] = (
            f"[가드레일: {reason_str}] "
            + (original_strategy or "신규 매수보다 관망 및 현금 확보를 우선합니다.")
        )
        analysis.setdefault("_guardrail_log", []).append(
            f"{current_label} -> {target_label} ({reason_str})"
        )
        guardrail_applied = True
        print(f"  [가드레일] {current_label} -> {target_label} ({reason_str})")

    # ── 관망/위험관리 시 BUY 시그널 무효화 ──────────────────────────────────
    final_label = analysis.get("strategy_stance", {}).get("label", "관망")
    if final_label in ("관망", "위험관리"):
        buy_neutralized = 0
        for sig in analysis.get("paper_trading_signals", []):
            if isinstance(sig, dict) and sig.get("action") == "BUY":
                sig["action"] = "WATCH"
                sig["virtual_entry_allowed"] = False
                buy_neutralized += 1
        if buy_neutralized:
            print(f"  [가드레일] 전략 '{final_label}' — BUY {buy_neutralized}건 WATCH로 하향")

    if not guardrail_applied and not active_reasons:
        print(f"  [가드레일] 조건 없음 — {current_label} 유지")

    return analysis
