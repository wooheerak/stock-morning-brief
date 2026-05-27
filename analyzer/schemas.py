"""
Pydantic v2 스키마 — Gemini 응답 JSON 구조 검증.
파싱 실패 시 기본값으로 폴백하여 브리핑이 중단되지 않도록 한다.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List


class KeyIssue(BaseModel):
    title: str = ""
    summary: str = ""
    implication: str = ""
    source: str = ""
    time: str = ""


class ShortTermStock(BaseModel):
    name: str = ""
    code: str = ""
    prev_change: str = ""
    trade_signal: str = "관망"
    action_guide: str = ""
    reason: str = ""
    stop_loss: str = ""
    avoid_chase: str = ""
    risk: str = ""

    @field_validator("trade_signal")
    @classmethod
    def check_trade_signal(cls, v: str) -> str:
        return v if v in {"추격가능", "눌림목대기", "관망"} else "관망"

    @field_validator("code")
    @classmethod
    def check_code(cls, v: str) -> str:
        """6자리 숫자가 아니면 빈 문자열로 → MorningBriefAnalysis에서 필터링"""
        return v if (v and v.isdigit() and len(v) == 6) else ""


class MidTermStock(BaseModel):
    name: str = ""
    code: str = ""
    category: str = "구조적성장"
    reason: str = ""
    risk: str = ""

    @field_validator("category")
    @classmethod
    def check_category(cls, v: str) -> str:
        return v if v in {"구조적성장", "이벤트드리븐", "수주기반", "가치"} else "구조적성장"

    @field_validator("code")
    @classmethod
    def check_code(cls, v: str) -> str:
        return v if (v and v.isdigit() and len(v) == 6) else ""


class StrategyStance(BaseModel):
    label: str = "관망"
    emoji: str = "🟡"
    cash_ratio: str = ""


class QuickSummary(BaseModel):
    one_line: str = ""
    action: str = ""
    check_top3: List[str] = Field(default_factory=list)


class MorningBriefAnalysis(BaseModel):
    market_sentiment: str = "중립"
    sentiment_score: int = Field(default=50, ge=0, le=100)
    sentiment_breakdown: str = ""
    key_issues: List[KeyIssue] = Field(default_factory=list)
    short_term_stocks: List[ShortTermStock] = Field(default_factory=list)
    mid_term_stocks: List[MidTermStock] = Field(default_factory=list)
    market_style: List[str] = Field(default_factory=list)
    strong_sectors: List[str] = Field(default_factory=list)
    weak_sectors: List[str] = Field(default_factory=list)
    strategy_stance: StrategyStance = Field(default_factory=StrategyStance)
    today_strategy: str = ""
    risk_factors: List[str] = Field(default_factory=list)
    checkpoints: List[str] = Field(default_factory=list)
    quick_summary: QuickSummary = Field(default_factory=QuickSummary)

    @field_validator("market_sentiment")
    @classmethod
    def check_sentiment(cls, v: str) -> str:
        return v if v in {"긍정", "중립", "부정"} else "중립"

    @field_validator("short_term_stocks")
    @classmethod
    def cap_short_stocks(cls, v: List[ShortTermStock]) -> List[ShortTermStock]:
        """코드 없는 종목 제거 + 최대 2개"""
        return [s for s in v if s.code][:2]

    @field_validator("mid_term_stocks")
    @classmethod
    def cap_mid_stocks(cls, v: List[MidTermStock]) -> List[MidTermStock]:
        """코드 없는 종목 제거 + 최대 3개"""
        return [s for s in v if s.code][:3]
