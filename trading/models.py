"""
페이퍼 트레이딩 데이터 모델.
브리핑 JSON → 시그널 → 가상 결과까지의 전 과정을 구조화한다.
"""
from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── 시그널 (AI 브리핑 → 매매 지시) ──────────────────────────────────────

class PaperSignal(BaseModel):
    """Gemini 가 반환하는 paper_trading_signals 의 단일 원소."""
    code: str
    name: str
    action: Literal["WATCH", "BUY", "SKIP"] = "WATCH"
    entry_type: Literal["PULLBACK", "BREAKOUT", "OPEN"] = "OPEN"
    virtual_entry_allowed: bool = True
    take_profit_pct: float = Field(default=3.0, ge=0.1, le=30.0)
    stop_loss_pct: float = Field(default=-2.0, le=-0.1, ge=-20.0)
    holding_period: Literal["DAY", "SWING"] = "DAY"
    confidence: int = Field(default=50, ge=0, le=100)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = str(v).strip()
        return v if re.match(r"^\d{6}$", v) else ""

    @field_validator("action")
    @classmethod
    def check_action(cls, v: str) -> str:
        return v if v in {"WATCH", "BUY", "SKIP"} else "WATCH"


class DailySignal(BaseModel):
    """하루치 브리핑에서 추출한 전체 트레이딩 컨텍스트."""
    date: str                           # YYYY-MM-DD
    time: str                           # HH:MM
    market_sentiment_score: int = Field(default=50, ge=0, le=100)
    strategy: str = "관망"
    cash_ratio: str = ""
    watch_sectors: List[str] = Field(default_factory=list)
    avoid_sectors: List[str] = Field(default_factory=list)
    candidates: List[PaperSignal] = Field(default_factory=list)


# ── 결과 (가상 체결 + 청산) ───────────────────────────────────────────────

class TradeResult(BaseModel):
    """단일 종목 페이퍼 트레이딩 결과."""
    date: str                           # 진입 날짜
    code: str
    name: str
    entry_price: float
    exit_price: Optional[float] = None
    return_rate: Optional[float] = None   # % (소수 2자리)
    result: Optional[Literal["WIN", "LOSS", "DRAW"]] = None
    exit_reason: Optional[Literal["TAKE_PROFIT", "STOP_LOSS", "EOD", "PENDING"]] = None
    take_profit_pct: float = 3.0
    stop_loss_pct: float = -2.0
    action: str = "WATCH"
    confidence: int = 50
    open_price: Optional[float] = None   # 당일 시가 (참고용)
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
