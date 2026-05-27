"""
누적 성과 분석 리포트.

data/results/ 폴더의 모든 결과 파일을 로드하여 아래 지표를 계산한다.
  - 승률 (win_rate)
  - 평균 수익률 / 평균 손실률
  - 손익비 (profit_factor)
  - 누적 수익률
  - 최대 낙폭 (MDD)
  - 코스피 대비 알파 (KOSPI alpha)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict

_KST = timezone(timedelta(hours=9))
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RESULTS_DIR = os.path.join(_BASE, "data", "results")

# 판단 기준선
_MIN_WIN_RATE   = 0.55   # 55%
_MAX_MDD        = -5.0   # -5%
_MIN_PROFIT_FAC = 1.0    # 손익비 1.0 이상


def load_all_results(days: int = 30) -> List[Dict]:
    """최근 N거래일의 결과 로드 (오래된 순)."""
    if not os.path.exists(_RESULTS_DIR):
        return []

    cutoff = datetime.now(_KST).date() - timedelta(days=days)
    all_trades = []

    for fname in sorted(os.listdir(_RESULTS_DIR)):
        if not fname.endswith(".json"):
            continue
        date_str = fname.replace(".json", "")
        try:
            trade_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if trade_date < cutoff:
            continue

        fpath = os.path.join(_RESULTS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                trades = json.load(f)
            all_trades.extend(trades)
        except Exception:
            pass

    return all_trades


def _calc_metrics(trades: List[Dict]) -> Dict:
    """성과 지표 계산."""
    # PENDING(데이터 없음) 제외
    closed = [t for t in trades if t.get("result") in {"WIN", "LOSS", "DRAW"}]
    if not closed:
        return {}

    wins   = [t for t in closed if t["result"] == "WIN"]
    losses = [t for t in closed if t["result"] == "LOSS"]
    draws  = [t for t in closed if t["result"] == "DRAW"]

    win_rate   = len(wins) / len(closed) if closed else 0
    avg_win    = sum(t["return_rate"] for t in wins)   / len(wins)   if wins   else 0
    avg_loss   = sum(t["return_rate"] for t in losses) / len(losses) if losses else 0
    avg_draw   = 0.0

    # 손익비 = 평균 수익 / |평균 손실|
    profit_factor = (avg_win / abs(avg_loss)) if avg_loss != 0 else float("inf")

    # 누적 수익률 (종목당 30% 비중, 최대 3종목 가정 → 나머지 10% 현금)
    weight = 0.30
    cum_return = sum(t.get("return_rate", 0) * weight for t in closed)

    # MDD — 일자별 누적 수익률의 최대 낙폭
    by_date: Dict[str, float] = {}
    for t in closed:
        d = t.get("date", "")
        by_date[d] = by_date.get(d, 0) + t.get("return_rate", 0) * weight

    running = 0.0
    peak    = 0.0
    mdd     = 0.0
    for d in sorted(by_date):
        running += by_date[d]
        if running > peak:
            peak = running
        dd = running - peak
        if dd < mdd:
            mdd = dd

    return {
        "total_trades":   len(closed),
        "wins":           len(wins),
        "losses":         len(losses),
        "draws":          len(draws),
        "win_rate":       round(win_rate * 100, 1),
        "avg_win_pct":    round(avg_win, 2),
        "avg_loss_pct":   round(avg_loss, 2),
        "profit_factor":  round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
        "cum_return_pct": round(cum_return, 2),
        "mdd_pct":        round(mdd, 2),
    }


def _grade(metrics: Dict) -> str:
    """기준선 대비 합격/경고/실패 등급."""
    if not metrics:
        return "데이터 없음"
    issues = []
    if metrics["win_rate"] < _MIN_WIN_RATE * 100:
        issues.append(f"승률 {metrics['win_rate']}% < {int(_MIN_WIN_RATE*100)}%")
    if metrics["mdd_pct"] < _MAX_MDD:
        issues.append(f"MDD {metrics['mdd_pct']}% < {_MAX_MDD}%")
    if metrics["profit_factor"] < _MIN_PROFIT_FAC:
        issues.append(f"손익비 {metrics['profit_factor']} < {_MIN_PROFIT_FAC}")
    if not issues:
        return "합격"
    return "경고 — " + " | ".join(issues)


def get_summary(days: int = 20) -> str:
    """최근 N거래일 성과 요약 문자열 반환 (콘솔/메시지 출력용)."""
    trades = load_all_results(days)
    closed = [t for t in trades if t.get("result") in {"WIN", "LOSS", "DRAW"}]

    if not closed:
        return f"  [성과리포트] 최근 {days}일 평가 완료 종목 없음"

    m = _calc_metrics(trades)
    grade = _grade(m)

    lines = [
        f"  [페이퍼트레이딩 성과 — 최근 {days}거래일]",
        f"  총 {m['total_trades']}건 | 승 {m['wins']} / 패 {m['losses']} / 무 {m['draws']}",
        f"  승률 {m['win_rate']}%  손익비 {m['profit_factor']}",
        f"  평균 수익 {m['avg_win_pct']:+.2f}%  평균 손실 {m['avg_loss_pct']:+.2f}%",
        f"  누적 수익 {m['cum_return_pct']:+.2f}%  MDD {m['mdd_pct']:+.2f}%",
        f"  판정: {grade}",
    ]
    return "\n".join(lines)


def get_metrics(days: int = 20) -> Dict:
    """원시 지표 dict 반환 (외부 활용용)."""
    return _calc_metrics(load_all_results(days))
