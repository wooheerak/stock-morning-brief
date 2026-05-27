"""
뉴스 기반 종목 후보 추출 + yfinance 실제 가격 수집.
AI가 종목을 '자유 생성'하지 않고, 실제 데이터가 있는 후보에서만 선택하도록 한다.
"""
import yfinance as yf
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

_KST = timezone(timedelta(hours=9))

# 유니버스: 뉴스에 자주 등장하는 주요 KOSPI/KOSDAQ 종목
# 형식: "종목명": ("코드6자리", "yfinance_티커")
STOCK_UNIVERSE: Dict[str, Tuple[str, str]] = {
    # 반도체/IT
    "삼성전자":           ("005930", "005930.KS"),
    "SK하이닉스":         ("000660", "000660.KS"),
    "삼성SDI":            ("006400", "006400.KS"),
    "삼성SDS":            ("018260", "018260.KS"),
    "대덕전자":           ("353200", "353200.KS"),
    "DB하이텍":           ("000990", "000990.KS"),
    "리노공업":           ("058470", "058470.KS"),
    # AI/플랫폼
    "네이버":             ("035420", "035420.KS"),
    "카카오":             ("035720", "035720.KS"),
    # 2차전지
    "LG에너지솔루션":     ("373220", "373220.KS"),
    "에코프로비엠":       ("247540", "247540.KQ"),
    "포스코퓨처엠":       ("003670", "003670.KS"),
    "에코프로":           ("086520", "086520.KQ"),
    # 조선/방산
    "한화에어로스페이스": ("012450", "012450.KS"),
    "HD현대중공업":       ("329180", "329180.KS"),
    "한국조선해양":       ("009540", "009540.KS"),
    "현대로템":           ("064350", "064350.KS"),
    # 자동차
    "현대차":             ("005380", "005380.KS"),
    "기아":               ("000270", "000270.KS"),
    "현대모비스":         ("012330", "012330.KS"),
    # 금융
    "KB금융":             ("105560", "105560.KS"),
    "신한지주":           ("055550", "055550.KS"),
    "미래에셋증권":       ("006800", "006800.KS"),
    # 바이오/헬스
    "삼성바이오로직스":   ("207940", "207940.KS"),
    "HLB":               ("028300", "028300.KQ"),
    "셀트리온":           ("068270", "068270.KS"),
    "유한양행":           ("000100", "000100.KS"),
    # 전력/에너지
    "LS일렉트릭":         ("010120", "010120.KS"),
    "HD현대일렉트릭":     ("267260", "267260.KS"),
    "한전KPS":            ("051600", "051600.KS"),
    # 철강/소재
    "POSCO홀딩스":        ("005490", "005490.KS"),
    "LG화학":             ("051910", "051910.KS"),
    "롯데케미칼":         ("011170", "011170.KS"),
    # 소비/유통
    "이마트":             ("139480", "139480.KS"),
    "LG전자":             ("066570", "066570.KS"),
}


def _find_mentioned(news_list: List[Dict]) -> List[str]:
    """뉴스 제목에서 유니버스 내 종목명 추출."""
    result = []
    for name in STOCK_UNIVERSE:
        norm = name.replace(" ", "")
        if any(norm in n.get("title", "").replace(" ", "") for n in news_list):
            result.append(name)
    return result


def _fetch_snapshot(name: str) -> Optional[Dict]:
    """단일 종목 전일 종가·거래량·이동평균 수집."""
    code, ticker = STOCK_UNIVERSE[name]
    try:
        hist = yf.Ticker(ticker).history(period="30d")
        if len(hist) < 2:
            return None

        closes  = hist["Close"]
        volumes = hist["Volume"]

        last    = float(closes.iloc[-1])
        prev    = float(closes.iloc[-2])
        vol     = int(volumes.iloc[-1])
        avg_vol = int(volumes.iloc[-20:].mean()) if len(hist) >= 20 else vol
        pct     = (last - prev) / prev * 100
        ma5     = float(closes.iloc[-5:].mean())  if len(hist) >= 5  else last
        ma20    = float(closes.iloc[-20:].mean()) if len(hist) >= 20 else last
        h52     = float(closes.max())
        l52     = float(closes.min())

        return {
            "name":         name,
            "code":         code,
            "close":        round(last),
            "change_pct":   round(pct, 2),
            "signal":       "▲" if pct > 0 else "▼" if pct < 0 else "━",
            "volume":       vol,
            "volume_ratio": round(vol / avg_vol, 2) if avg_vol else 1.0,
            "ma5":          round(ma5),
            "ma20":         round(ma20),
            "above_ma5":    last > ma5,
            "above_ma20":   last > ma20,
            "high_52w":     round(h52),
            "low_52w":      round(l52),
        }
    except Exception as e:
        print(f"  [종목 스크리너] {name} 수집 실패: {e}")
        return None


def screen_candidates(news_list: List[Dict], max_count: int = 8) -> List[Dict]:
    """
    뉴스 언급 종목에서 후보 목록 생성.
    - 거래량배율 높은 순 정렬 (수급 관심도)
    - max_count 개 제한
    Returns: list of snapshot dicts
    """
    mentioned = _find_mentioned(news_list)
    print(f"  [종목 스크리너] 언급 종목({len(mentioned)}개): "
          f"{', '.join(mentioned) if mentioned else '없음'}")

    candidates = []
    for name in mentioned[:max_count + 4]:   # 여유분 조회 후 잘라냄
        snap = _fetch_snapshot(name)
        if snap:
            candidates.append(snap)

    # 거래량배율 높은 순
    candidates.sort(key=lambda x: x["volume_ratio"], reverse=True)
    result = candidates[:max_count]
    print(f"  [종목 스크리너] 후보 확정({len(result)}개): "
          f"{', '.join(c['name'] for c in result) if result else '없음'}")
    return result


def format_candidates_for_prompt(candidates: List[Dict]) -> str:
    """프롬프트 삽입용 후보 종목 텍스트 생성."""
    if not candidates:
        return "후보 없음 — 뉴스에 유니버스 내 종목 미언급. short_term_stocks와 mid_term_stocks는 빈 배열로 반환."

    lines = []
    for c in candidates:
        if c["above_ma5"] and c["above_ma20"]:
            ma_flag = "MA5·MA20 위(강세)"
        elif c["above_ma5"]:
            ma_flag = "MA5 위·MA20 아래"
        elif c["above_ma20"]:
            ma_flag = "MA5 아래·MA20 위"
        else:
            ma_flag = "MA5·MA20 아래(약세)"

        lines.append(
            f"- {c['name']}({c['code']}): "
            f"전일 {c['signal']}{c['change_pct']:+.1f}%  "
            f"종가 {c['close']:,}원  "
            f"거래량배율 {c['volume_ratio']:.1f}x  "
            f"{ma_flag}  "
            f"52주 {c['low_52w']:,}~{c['high_52w']:,}"
        )
    return "\n".join(lines)
