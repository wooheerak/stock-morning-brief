"""
AI 브리핑 JSON → 페이퍼 트레이딩 시그널 파싱 + 저장.

data/signals/YYYY-MM-DD.json 으로 저장한다.
"""
import json
import os
from typing import Dict

from .models import DailySignal, PaperSignal

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SIGNALS_DIR = os.path.join(_BASE, "data", "signals")


def parse_and_save(analysis: Dict, date: str, time: str) -> DailySignal:
    """
    AI 분석 결과에서 시그널을 추출하고 파일로 저장한다.

    Parameters
    ----------
    analysis : dict   analyze_morning_brief() 반환값
    date     : str    YYYY-MM-DD
    time     : str    HH:MM

    Returns
    -------
    DailySignal 저장된 시그널 객체
    """
    os.makedirs(_SIGNALS_DIR, exist_ok=True)

    stance = analysis.get("strategy_stance", {})
    raw_candidates = analysis.get("paper_trading_signals", [])

    # 유효한 시그널만 (code 검증)
    valid_candidates = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        try:
            sig = PaperSignal.model_validate(raw)
            if sig.code:   # 코드 없는 종목 제외
                valid_candidates.append(sig)
        except Exception as e:
            print(f"  [시그널파서] 종목 파싱 오류 (건너뜀): {e}")

    # 신뢰도 기준 정렬 (높은 것 먼저)
    valid_candidates.sort(key=lambda x: x.confidence, reverse=True)
    # 최대 3개 (프롬프트 지시와 일관성)
    valid_candidates = valid_candidates[:3]

    signal = DailySignal(
        date=date,
        time=time,
        market_sentiment_score=int(analysis.get("sentiment_score", 50)),
        strategy=stance.get("label", "관망"),
        cash_ratio=stance.get("cash_ratio", ""),
        watch_sectors=analysis.get("strong_sectors", []),
        avoid_sectors=analysis.get("weak_sectors", []),
        candidates=valid_candidates,
    )

    path = os.path.join(_SIGNALS_DIR, f"{date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(signal.model_dump(), f, ensure_ascii=False, indent=2)

    tradable = sum(1 for c in valid_candidates if c.virtual_entry_allowed)
    print(f"  [시그널] {path} 저장 완료 / 총 {len(valid_candidates)}개 (가상매매 {tradable}개)")
    return signal


def load_signal(date: str) -> DailySignal | None:
    """저장된 시그널 로드. 없으면 None 반환."""
    path = os.path.join(_SIGNALS_DIR, f"{date}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DailySignal.model_validate(data)
    except Exception as e:
        print(f"  [시그널] {date} 로드 실패: {e}")
        return None
