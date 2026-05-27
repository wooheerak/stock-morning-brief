"""
전략 가드레일 — AI 분석 결과를 시장 데이터로 후처리 보정.

① 전략 스탠스 강제 하향 (승격 금지, 보수적 방향만)
② 심리점수 floor/ceiling 보정 (실제 지수 방향 기반)
③ 시간대별 금지 표현 클린업 (장중 브리핑에서 "전일 코스피" 등 제거)
④ 가드레일 적용 내역 구조화 저장 (_guardrail_info)
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# ── 스탠스 레벨 (높을수록 공격적) ────────────────────────────────────────
_LEVELS = {"적극매수": 3, "보수적매수": 2, "관망": 1, "위험관리": 0}
_EMOJI  = {"적극매수": "🟢", "보수적매수": "🟡", "관망": "🟡", "위험관리": "🔴"}
_CASH   = {
    "적극매수":  "10~20%",
    "보수적매수": "30~40%",
    "관망":      "50~60%",
    "위험관리":  "60% 이상",
}

# 시간대별 금지 표현 (09:00 이후)
_INTRADAY_BAN = [
    (re.compile(r'전일\s*코스피'), "코스피"),
    (re.compile(r'전일\s*코스닥'), "코스닥"),
    (re.compile(r'전일\s*지수'), "지수"),
    (re.compile(r'장\s*초반\s*방향'), "장중 방향"),
    (re.compile(r'시초가\s*방향'), "장중 흐름"),
    (re.compile(r'시초가'), "장중가"),
]

# 장 마감 후(15:30 이후) 금지 표현
_POSTMARKET_BAN = [
    (re.compile(r'시초가'), "장중가"),
    (re.compile(r'장\s*초반'), "이전 장"),
    (re.compile(r'갭\s*(상승|하락)'), "전일 대비"),
]


# ── 규칙 평가 ─────────────────────────────────────────────────────────────

def _check_stance_rules(
    kospi_pct: float,
    kosdaq_pct: float,
    vix_pct: float,
    usdkrw_val: float,
    score: int,
) -> List[Tuple[str, str]]:
    """전략 하향 규칙 → [(target_label, reason)] 목록."""
    hits: List[Tuple[str, str]] = []

    # R1: 코스피 3%+ vs 코스닥 -2%- 대형주 쏠림
    if kospi_pct >= 3 and kosdaq_pct <= -2:
        hits.append(("보수적매수", f"코스피 {kospi_pct:+.1f}% vs 코스닥 {kosdaq_pct:+.1f}% 쏠림"))

    # R2: VIX 상승 + 환율 1,500원 이상
    if vix_pct > 0 and usdkrw_val >= 1_500:
        hits.append(("관망", f"VIX {vix_pct:+.1f}% + 달러/원 {usdkrw_val:,.0f}원"))

    # R3: R1 + VIX 동시
    if kospi_pct >= 3 and kosdaq_pct <= -2 and vix_pct > 0:
        hits.append(("관망", "코스피/코스닥 쏠림 + VIX 동시 상승"))

    # R4: 심리점수 < 45 → 적극매수 금지
    if score < 45:
        hits.append(("보수적매수", f"심리점수 {score}점 < 45"))

    # R5: 심리점수 < 35 → 관망 강제
    if score < 35:
        hits.append(("관망", f"심리점수 {score}점 < 35"))

    return hits


def _correct_sentiment_score(
    score: int,
    kospi_pct: float,
    kosdaq_pct: float,
    breadth_score: int = 50,
    risk_score: int = 30,
) -> Tuple[int, Optional[str]]:
    """
    실제 지수 방향·시장폭과 과도하게 괴리된 심리점수를 보정한다.

    우선순위
    --------
    1. 시장폭(Breadth) 기반 ceiling  ← 신규 (좁은 장세에서 과도 낙관 방지)
    2. 시장 방향 기반 floor / ceiling

    규칙:
    [Breadth ceiling]
    - breadth < 25 → ceiling 45  (매우좁음: 반도체 1~2개만 오르는 장)
    - breadth < 40 AND risk ≥ 65 → ceiling 48
    - breadth < 40 → ceiling 52

    [Market direction floor/ceiling]
    - 코스피 > +2%: floor 40
    - 코스피 > +1%: floor 36
    - 코스피/코스닥 모두 양수: floor 38
    - 코스피 < -2%: ceiling 52

    Returns
    -------
    (corrected_score, reason_str or None)
    """
    corrected = score
    reason: Optional[str] = None

    # ── 1순위: 시장폭 기반 ceiling ───────────────────────────────────────
    if breadth_score < 25 and corrected > 45:
        corrected = 45
        reason = f"시장폭 {breadth_score}점(매우좁음) → ceiling 45"
    elif breadth_score < 40 and risk_score >= 65 and corrected > 48:
        corrected = 48
        reason = f"시장폭 {breadth_score}점(좁음)·리스크 {risk_score}점 → ceiling 48"
    elif breadth_score < 40 and corrected > 52:
        corrected = 52
        reason = f"시장폭 {breadth_score}점(좁음) → ceiling 52"

    # ── 2순위: 시장 방향 floor/ceiling (breadth ceiling 미발동 시만) ──────
    elif kospi_pct > 2.0 and corrected < 40:
        corrected = 40
        reason = f"코스피 {kospi_pct:+.1f}% 상승 → floor 40"
    elif kospi_pct > 1.0 and corrected < 36:
        corrected = 36
        reason = f"코스피 {kospi_pct:+.1f}% 상승 → floor 36"
    elif kospi_pct > 0 and kosdaq_pct > 0 and corrected < 38:
        corrected = 38
        reason = f"코스피/코스닥 모두 양수 → floor 38"
    elif kospi_pct < -2.0 and corrected > 52:
        corrected = 52
        reason = f"코스피 {kospi_pct:+.1f}% 하락 → ceiling 52"

    return corrected, reason


def _clean_time_text(text: str, briefing_hour: int) -> str:
    """브리핑 시간대에 맞지 않는 표현 치환."""
    if not isinstance(text, str):
        return text
    ban_list = []
    if briefing_hour >= 9:
        ban_list.extend(_INTRADAY_BAN)
    if briefing_hour >= 15:
        ban_list.extend(_POSTMARKET_BAN)
    for pattern, replacement in ban_list:
        text = pattern.sub(replacement, text)
    return text


# ── 공개 API ──────────────────────────────────────────────────────────────

def apply_strategy_guardrails(
    analysis: Dict,
    overseas: Dict,
    korean: Dict,
    briefing_time: str = "",
) -> Dict:
    """
    AI 분석 후처리: 전략 하향 + 점수 보정 + 시간대 텍스트 클린업.

    Parameters
    ----------
    analysis      : dict  analyze_morning_brief() 반환값
    overseas      : dict  fetch_overnight_summary() 반환값
    korean        : dict  fetch_korean_index() 반환값
    briefing_time : str   "HH:MM" 형식 (장중 텍스트 클린업용)

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

    # 시장폭 정보 (analyze_morning_brief가 주입한 _breadth_info)
    breadth_info  = analysis.get("_breadth_info", {})
    breadth_score = int(breadth_info.get("breadth_score", 50))
    risk_score_b  = int(breadth_info.get("risk_score", 30))

    try:
        brief_hour = int(briefing_time.split(":")[0]) if briefing_time else 0
    except Exception:
        brief_hour = 0

    # ── 1. 심리점수 보정 ─────────────────────────────────────────────────
    corrected_score, score_reason = _correct_sentiment_score(
        score, kospi_pct, kosdaq_pct, breadth_score, risk_score_b
    )
    score_changed = corrected_score != score
    if score_changed:
        analysis["sentiment_score"] = corrected_score
        print(f"  [가드레일] 심리점수 {score} -> {corrected_score} ({score_reason})")

    # ── 2. 전략 스탠스 하향 ──────────────────────────────────────────────
    hits = _check_stance_rules(kospi_pct, kosdaq_pct, vix_pct, usdkrw_val, corrected_score)

    target_label  = current_label
    target_level  = current_level
    active_reasons: List[str] = []

    for label, reason in hits:
        lv = _LEVELS.get(label, 1)
        if lv < target_level:
            target_label   = label
            target_level   = lv
            active_reasons = [reason]
        elif lv == target_level and reason not in active_reasons:
            active_reasons.append(reason)

    stance_changed = target_level < current_level and target_label != current_label
    if stance_changed:
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
        print(f"  [가드레일] 전략 {current_label} -> {target_label} ({reason_str})")
    else:
        if not active_reasons:
            print(f"  [가드레일] 조건 없음 — {current_label} 유지")

    # ── 3. 관망/위험관리 시 BUY 무효화 ─────────────────────────────────────
    final_label = analysis.get("strategy_stance", {}).get("label", "관망")
    buy_count = 0
    if final_label in ("관망", "위험관리"):
        for sig in analysis.get("paper_trading_signals", []):
            if isinstance(sig, dict) and sig.get("action") == "BUY":
                sig["action"] = "WATCH"
                sig["virtual_entry_allowed"] = False
                buy_count += 1
        if buy_count:
            print(f"  [가드레일] 전략 '{final_label}' — BUY {buy_count}건 WATCH 하향")

    # ── 4. 장중 텍스트 클린업 ────────────────────────────────────────────
    text_cleaned = False
    if brief_hour >= 9:
        for field in ("today_strategy", "sentiment_breakdown"):
            original = analysis.get(field, "")
            cleaned  = _clean_time_text(original, brief_hour)
            if cleaned != original:
                analysis[field] = cleaned
                text_cleaned = True
        for issue in analysis.get("key_issues", []):
            if isinstance(issue, dict):
                for k in ("summary", "implication"):
                    orig = issue.get(k, "")
                    issue[k] = _clean_time_text(orig, brief_hour)
        for i, cp in enumerate(analysis.get("checkpoints", [])):
            analysis["checkpoints"][i] = _clean_time_text(cp, brief_hour)
        if text_cleaned:
            print(f"  [가드레일] {brief_hour}시 이후 표현 정리 완료")

    # ── 5. 구조화 로그 저장 (_guardrail_info) ────────────────────────────
    analysis["_guardrail_info"] = {
        "applied":         stance_changed or score_changed,
        "before_label":    current_label,
        "after_label":     final_label,
        "before_score":    score,
        "after_score":     corrected_score,
        "score_corrected": score_changed,
        "reasons":         active_reasons,
        "buy_neutralized": buy_count,
        "text_cleaned":    text_cleaned,
    }

    return analysis
