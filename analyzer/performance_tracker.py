"""
종목 추천 성과 기록 및 추적.
매일 추천 종목을 data/performance_log.json에 저장하고,
N일 후 실제 수익률을 자동 계산한다.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

_KST = timezone(timedelta(hours=9))
_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "performance_log.json")

# 성과 평가 기준일 (추천 후 N 거래일)
_EVAL_DAYS = (1, 3, 5)


# ─────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────

def _load_log() -> List[Dict]:
    if os.path.exists(_LOG_PATH):
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_log(log: List[Dict]) -> None:
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    with open(_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _ticker_for(code: str) -> str:
    """종목코드 → yfinance 티커 추론 (KOSDAQ은 .KQ, 나머지 .KS)"""
    from scraper.stock_screener import STOCK_UNIVERSE
    for name, (c, ticker) in STOCK_UNIVERSE.items():
        if c == code:
            return ticker
    # 유니버스에 없으면 KS 가정
    return f"{code}.KS"


def _fetch_close(code: str, days_back: int) -> Optional[float]:
    """N일 전 종가 조회 (yfinance)."""
    try:
        import yfinance as yf
        ticker = _ticker_for(code)
        hist = yf.Ticker(ticker).history(period=f"{days_back + 5}d")
        if len(hist) < days_back:
            return None
        return round(float(hist["Close"].iloc[-days_back]), 0)
    except Exception:
        return None


# ─────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────

def save_recommendations(analysis: Dict, brief_date: str) -> None:
    """
    오늘 추천 종목을 로그에 추가.
    brief_date: 'YYYY-MM-DD' 형식
    """
    entries = []

    for s in analysis.get("short_term_stocks", []):
        code = s.get("code", "")
        if not code:
            continue
        entries.append({
            "date":         brief_date,
            "type":         "short",
            "name":         s.get("name", ""),
            "code":         code,
            "signal":       s.get("trade_signal", ""),
            "reason":       s.get("reason", ""),
            "entry_close":  None,   # 당일 종가 (다음 평가 시 채워짐)
            "perf_1d":      None,
            "perf_3d":      None,
            "perf_5d":      None,
        })

    for s in analysis.get("mid_term_stocks", []):
        code = s.get("code", "")
        if not code:
            continue
        entries.append({
            "date":         brief_date,
            "type":         "mid",
            "name":         s.get("name", ""),
            "code":         code,
            "category":     s.get("category", ""),
            "reason":       s.get("reason", ""),
            "entry_close":  None,
            "perf_1d":      None,
            "perf_3d":      None,
            "perf_5d":      None,
        })

    if not entries:
        return

    log = _load_log()
    log.extend(entries)
    _save_log(log)
    print(f"  [성과 추적] {len(entries)}개 종목 기록 (date={brief_date})")


def evaluate_and_update() -> Optional[str]:
    """
    과거 추천 종목의 성과를 계산해 로그 업데이트.
    Returns: 성과 요약 문자열 (없으면 None)
    """
    log = _load_log()
    if not log:
        return None

    today = datetime.now(_KST).date()
    updated_count = 0
    summaries: List[str] = []

    for entry in log:
        try:
            rec_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        except ValueError:
            continue

        calendar_days = (today - rec_date).days
        code = entry.get("code", "")
        if not code:
            continue

        # entry_close 아직 없으면 추천일 당일 종가로 채우기
        if entry.get("entry_close") is None and calendar_days >= 1:
            close = _fetch_close(code, calendar_days)
            if close:
                entry["entry_close"] = close

        entry_close = entry.get("entry_close")
        if not entry_close:
            continue

        # N일 성과 계산
        for n in _EVAL_DAYS:
            key = f"perf_{n}d"
            if entry.get(key) is not None:
                continue   # 이미 계산됨
            if calendar_days < n:
                continue   # 아직 N일이 안 됨

            close_n = _fetch_close(code, calendar_days - n)
            if close_n:
                perf = (close_n - entry_close) / entry_close * 100
                entry[key] = round(perf, 2)
                updated_count += 1
                summaries.append(
                    f"{entry['name']}({entry['type']}) +{n}일: {perf:+.1f}%"
                )

    if updated_count:
        _save_log(log)
        print(f"  [성과 추적] {updated_count}건 성과 업데이트")

    if summaries:
        return "📊 추천 성과\n" + "\n".join(f"  • {s}" for s in summaries)
    return None


def get_recent_summary(days: int = 30) -> str:
    """최근 N일 추천 성과 요약 텍스트 반환 (디버깅/보고용)."""
    log = _load_log()
    if not log:
        return "기록 없음"

    today = datetime.now(_KST).date()
    cutoff = today - timedelta(days=days)

    lines = [f"최근 {days}일 추천 성과 요약"]
    for entry in log:
        try:
            d = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < cutoff:
            continue

        perfs = []
        for n in _EVAL_DAYS:
            v = entry.get(f"perf_{n}d")
            if v is not None:
                perfs.append(f"{n}일:{v:+.1f}%")

        lines.append(
            f"  {entry['date']} [{entry['type']}] {entry['name']}({entry['code']})"
            + (f" → {' / '.join(perfs)}" if perfs else " → 평가 대기")
        )

    return "\n".join(lines) if len(lines) > 1 else "해당 기간 기록 없음"
