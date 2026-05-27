import yfinance as yf
from datetime import datetime, timedelta, timezone
from typing import Dict

_KST = timezone(timedelta(hours=9))

MAJOR_INDICES = {
    "나스닥": "^IXIC",
    "S&P500": "^GSPC",
    "다우존스": "^DJI",
    "필라델피아반도체(SOX)": "^SOX",
    "VIX(공포지수)": "^VIX",
}

KEY_STOCKS = {
    "엔비디아": "NVDA",
    "테슬라": "TSLA",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
}

FX = {
    "달러/원": "USDKRW=X",
    "달러/엔": "JPY=X",
}

BONDS = {
    "미국채10년물": "^TNX",
}

COMMODITIES = {
    "WTI원유": "CL=F",    # $/barrel
    "금":      "GC=F",    # $/oz
    "구리":    "HG=F",    # $/lb
}


def _get_change(ticker: str) -> Dict:
    data = yf.Ticker(ticker)
    hist = data.history(period="2d")
    if len(hist) < 2:
        return {}
    prev = hist["Close"].iloc[-2]
    last = hist["Close"].iloc[-1]
    pct = ((last - prev) / prev) * 100
    return {
        "value": round(last, 2),
        "change_pct": round(pct, 2),
        "signal": "▲" if pct > 0 else "▼" if pct < 0 else "━",
    }


def _get_bond_change(ticker: str) -> Dict:
    """채권 금리용 — change_bp(basis points) 별도 계산"""
    data = yf.Ticker(ticker)
    hist = data.history(period="2d")
    if len(hist) < 2:
        return {}
    prev = hist["Close"].iloc[-2]
    last = hist["Close"].iloc[-1]
    change_pp = last - prev          # percentage point 변화
    change_bp = round(change_pp * 100)   # basis points
    change_pct = ((last - prev) / prev) * 100
    return {
        "value": round(last, 2),
        "change_pct": round(change_pct, 2),
        "change_bp": change_bp,
        "signal": "▲" if change_pp > 0 else "▼" if change_pp < 0 else "━",
        "display": f"{round(last, 2):.2f}%",
    }


def fetch_overnight_summary() -> Dict:
    """미국 시장 오버나이트 요약 (지수 + 주요 종목 + 환율)"""
    fetch_time = datetime.now(_KST).strftime("%Y/%m/%d %H:%M")
    result = {
        "indices": {},
        "stocks": {},
        "fx": {},
        "fetched_at": fetch_time,
        "data_as_of": "전일 미국장 마감 기준",
    }

    for name, ticker in MAJOR_INDICES.items():
        try:
            result["indices"][name] = _get_change(ticker)
        except Exception as e:
            print(f"[야후파이낸스] {name} 실패: {e}")

    for name, ticker in KEY_STOCKS.items():
        try:
            result["stocks"][name] = _get_change(ticker)
        except Exception as e:
            print(f"[야후파이낸스] {name} 실패: {e}")

    for name, ticker in FX.items():
        try:
            result["fx"][name] = _get_change(ticker)
        except Exception as e:
            print(f"[야후파이낸스] {name} 실패: {e}")

    result["bonds"] = {}
    for name, ticker in BONDS.items():
        try:
            result["bonds"][name] = _get_bond_change(ticker)
        except Exception as e:
            print(f"[야후파이낸스] {name} 실패: {e}")

    result["commodities"] = {}
    for name, ticker in COMMODITIES.items():
        try:
            result["commodities"][name] = _get_change(ticker)
        except Exception as e:
            print(f"[야후파이낸스] {name} 실패: {e}")

    return result


def fetch_korean_index() -> Dict:
    """코스피/코스닥 전일 마감"""
    indices = {"코스피": "^KS11", "코스닥": "^KQ11"}
    result = {}
    for name, ticker in indices.items():
        try:
            result[name] = _get_change(ticker)
        except Exception as e:
            print(f"[코스피/코스닥] {name} 실패: {e}")
    return result


if __name__ == "__main__":
    s = fetch_overnight_summary()
    for name, d in s["indices"].items():
        print(f"{name}: {d['signal']} {d['change_pct']:+.2f}%")
    for name, d in s["fx"].items():
        print(f"{name}: {d['value']:,.1f} {d['signal']} {d['change_pct']:+.2f}%")
