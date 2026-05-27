"""
가상 매매 체결 + 청산 평가.

진입: 당일 시가(Open) — 브리핑(07:30) 이후 장 시작(09:00) 기준
청산 우선순위: 익절가 도달 → 손절가 도달 → 종가 청산(EOD)
데이터: yfinance (한국 주식 .KS / .KQ)

data/results/YYYY-MM-DD.json 으로 저장한다.
"""
from __future__ import annotations

import json
import os
from datetime import date as _date_type, timedelta
from typing import List, Optional

import yfinance as yf

from .models import DailySignal, TradeResult
from .signal_parser import load_signal

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RESULTS_DIR = os.path.join(_BASE, "data", "results")


# ── 종목코드 → yfinance 티커 매핑 ────────────────────────────────────────

def _get_ticker(code: str) -> str:
    """코드 → yfinance 티커 (STOCK_UNIVERSE 우선, 없으면 .KS 폴백)"""
    try:
        from scraper.stock_screener import STOCK_UNIVERSE
        for _name, (c, t) in STOCK_UNIVERSE.items():
            if c == code:
                return t
    except Exception:
        pass
    return f"{code}.KS"


def _fetch_ohlc(ticker: str, trade_date: str) -> Optional[dict]:
    """특정 날짜의 OHLC 데이터 조회. 없으면 None."""
    try:
        hist = yf.Ticker(ticker).history(period="10d")
        if hist.empty:
            return None
        for idx, row in hist.iterrows():
            if str(idx.date()) == trade_date:
                return {
                    "open":  float(row["Open"]),
                    "high":  float(row["High"]),
                    "low":   float(row["Low"]),
                    "close": float(row["Close"]),
                }
    except Exception:
        pass
    return None


def _evaluate_trade(
    ohlc: dict,
    take_profit_pct: float,
    stop_loss_pct: float,
) -> tuple[float, str, str]:
    """OHLC + TP/SL → (exit_price, exit_reason, result)

    로직:
    1. 시가(Open) 진입
    2. 고가(High)가 TP 도달 시 → TAKE_PROFIT / WIN
    3. 저가(Low)가 SL 도달 시 → STOP_LOSS / LOSS
    4. 둘 다 도달하면 TP 우선 (낙관적 가정, 보수 추정 원하면 SL 우선으로 변경)
    5. 미도달 → 종가(Close) 청산 / EOD
    """
    entry = ohlc["open"]
    tp_price = entry * (1 + take_profit_pct / 100)
    sl_price = entry * (1 + stop_loss_pct / 100)

    hit_tp = ohlc["high"] >= tp_price
    hit_sl = ohlc["low"]  <= sl_price

    if hit_tp and hit_sl:
        # 일봉 OHLC에서는 고저 발생 순서 불명 → 보수적 검증: 손절 우선
        exit_price  = round(sl_price)
        exit_reason = "STOP_LOSS"
        result      = "LOSS"
    elif hit_tp:
        exit_price  = round(tp_price)
        exit_reason = "TAKE_PROFIT"
        result      = "WIN"
    elif hit_sl:
        exit_price  = round(sl_price)
        exit_reason = "STOP_LOSS"
        result      = "LOSS"
    else:
        exit_price  = round(ohlc["close"])
        exit_reason = "EOD"
        rr = (ohlc["close"] - entry) / entry * 100
        result = "WIN" if rr > 0.1 else "LOSS" if rr < -0.1 else "DRAW"

    return exit_price, exit_reason, result


# ── 공개 API ─────────────────────────────────────────────────────────────

def evaluate_date(trade_date: str) -> List[TradeResult]:
    """
    특정 거래일의 시그널을 실제 OHLC 데이터로 평가하고 결과를 저장한다.

    Parameters
    ----------
    trade_date : str  YYYY-MM-DD

    Returns
    -------
    List[TradeResult]  평가된 결과 목록 (빈 리스트면 시그널 없거나 데이터 없음)
    """
    signal: Optional[DailySignal] = load_signal(trade_date)
    if signal is None:
        print(f"  [페이퍼트레이딩] {trade_date} 시그널 없음 — 건너뜀")
        return []

    # 장중 브리핑 체크 (09:00~15:30 사이 생성된 시그널은 시가 진입 불가)
    try:
        h, m = map(int, signal.time.split(":"))
        is_intraday = (9 <= h < 15) or (h == 15 and m <= 30)
    except Exception:
        is_intraday = False

    if is_intraday:
        print(f"  [페이퍼트레이딩] {trade_date} {signal.time} 장중 브리핑 "
              f"— 시가 진입 불가, 평가 건너뜀 (사유: 과거 시가 역산 왜곡)")
        return []

    results: List[TradeResult] = []

    for cand in signal.candidates:
        if not cand.virtual_entry_allowed:
            print(f"  [페이퍼트레이딩] {cand.name} virtual_entry_allowed=False — 건너뜀")
            continue

        ticker = _get_ticker(cand.code)
        ohlc = _fetch_ohlc(ticker, trade_date)

        if ohlc is None:
            print(f"  [페이퍼트레이딩] {cand.name}({ticker}) {trade_date} 가격 데이터 없음")
            results.append(TradeResult(
                date=trade_date,
                code=cand.code,
                name=cand.name,
                entry_price=0,
                exit_reason="PENDING",
                take_profit_pct=cand.take_profit_pct,
                stop_loss_pct=cand.stop_loss_pct,
                action=cand.action,
                confidence=cand.confidence,
            ))
            continue

        exit_price, exit_reason, result_label = _evaluate_trade(
            ohlc, cand.take_profit_pct, cand.stop_loss_pct
        )
        entry = round(ohlc["open"])
        ret = round((exit_price - entry) / entry * 100, 2) if entry else 0.0

        tr = TradeResult(
            date=trade_date,
            code=cand.code,
            name=cand.name,
            entry_price=entry,
            exit_price=exit_price,
            return_rate=ret,
            result=result_label,
            exit_reason=exit_reason,
            take_profit_pct=cand.take_profit_pct,
            stop_loss_pct=cand.stop_loss_pct,
            action=cand.action,
            confidence=cand.confidence,
            open_price=round(ohlc["open"]),
            high_price=round(ohlc["high"]),
            low_price=round(ohlc["low"]),
            close_price=round(ohlc["close"]),
        )
        results.append(tr)
        icon = "WIN" if result_label == "WIN" else "LOSS" if result_label == "LOSS" else "DRAW"
        print(f"  [{icon}] {cand.name}({cand.code}): "
              f"진입 {entry:,} / 청산 {exit_price:,} ({ret:+.2f}%) [{exit_reason}]")

    # 결과 저장
    if results:
        os.makedirs(_RESULTS_DIR, exist_ok=True)
        path = os.path.join(_RESULTS_DIR, f"{trade_date}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in results], f, ensure_ascii=False, indent=2)
        wins  = sum(1 for r in results if r.result == "WIN")
        total = sum(1 for r in results if r.result in {"WIN", "LOSS", "DRAW"})
        print(f"  [페이퍼트레이딩] {trade_date} 결과 저장 → {wins}/{total} 승")

    return results


def get_last_trading_date(ref_date_str: str | None = None) -> str:
    """기준일 기준으로 가장 최근 거래일(평일) 반환.
    ref_date_str 이 None 이면 오늘 KST 기준.
    """
    from datetime import datetime, timezone, timedelta
    _KST = timezone(timedelta(hours=9))
    if ref_date_str:
        d = _date_type.fromisoformat(ref_date_str)
    else:
        d = datetime.now(_KST).date()

    # 오늘이 월요일이면 -3일(금요일), 일요일이면 -2일, 토요일이면 -1일
    # 그 외 평일이면 -1일
    delta = 1
    if d.weekday() == 0:   # 월요일
        delta = 3
    elif d.weekday() == 6: # 일요일
        delta = 2
    elif d.weekday() == 5: # 토요일
        delta = 1

    return str(d - timedelta(days=delta))
