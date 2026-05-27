import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

_KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def _filter_recent_news(news_list: list, max_hours: int = 36) -> list:
    """최근 N시간 이내 뉴스만 유지. 시간 정보 없는 기사는 항상 포함."""
    cutoff = _now_kst() - timedelta(hours=max_hours)
    kept, dropped = [], 0
    for n in news_list:
        t = n.get("time", "")
        if not t:
            kept.append(n)
            continue
        try:
            dt = datetime.strptime(t[:16], "%Y/%m/%d %H:%M")
            if dt >= cutoff:
                kept.append(n)
            else:
                dropped += 1
        except ValueError:
            kept.append(n)   # 파싱 실패 시 포함
    if dropped:
        print(f"  → 오래된 뉴스 {dropped}건 제외 (36시간 초과)")
    return kept

from scraper.naver_finance import fetch_market_news as naver_news, fetch_korean_index, fetch_investor_trend
from scraper.hankyung import fetch_market_news as hankyung_news
from scraper.yahoo_finance import fetch_overnight_summary
from scraper.validator import validate_market_data
from analyzer.claude_analyzer import analyze_morning_brief, analyze_watchlist
from analyzer.performance_tracker import save_recommendations, evaluate_and_update
from messenger.message_formatter import format_morning_brief, format_watchlist_brief
from messenger.kakao_api import send_to_me, refresh_access_token

load_dotenv()

WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "data", "watchlist.json")


def load_watchlist() -> dict:
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}}


def run_morning_brief():
    print(f"[{_now_kst().strftime('%Y-%m-%d %H:%M:%S')} KST] 모닝 브리핑 시작")

    # 카카오 토큰 갱신 (access_token 6시간 만료 → 매 실행 시 refresh_token으로 재발급)
    tokens = refresh_access_token()
    if tokens.get("access_token"):
        os.environ["KAKAO_ACCESS_TOKEN"] = tokens["access_token"]

    # 1. 데이터 수집
    print("뉴스 수집 중...")
    news = naver_news(12) + hankyung_news(8)
    print(f"  → 총 {len(news)}건 수집")
    news = _filter_recent_news(news)
    print(f"  → 필터 후 {len(news)}건")

    print("시장 데이터 수집 중...")
    overseas = fetch_overnight_summary()
    korean = fetch_korean_index()

    # 투자자별 수급 수집 (전일 외국인/기관 순매수)
    print("투자자 수급 수집 중...")
    overseas["investor_trend"] = fetch_investor_trend()

    # 국내 지수 이중 검증 결과 출력 (내부 일관성 + yfinance 교차)
    for w in korean.get("_warnings", []):
        print(f"  {w}")

    # 데이터 검증 (범위 이탈 / 파싱 오류 / 수집 실패 통합 체크)
    print("데이터 검증 중...")
    critical_error, warnings = validate_market_data(overseas, korean)
    for w in warnings:
        print(f"  {w}")
    if critical_error:
        raise ValueError(
            "[데이터 검증 실패] 핵심 시장 데이터 이상 감지 — 브리핑 중단.\n"
            + "\n".join(warnings)
        )

    # 2. AI 분석
    print("Claude AI 분석 중...")
    analysis = analyze_morning_brief(overseas, korean, news)

    # 3. 메시지 포맷
    message = format_morning_brief(analysis, overseas, korean)

    # 4. 관심종목 분석 추가 (등록된 종목 있을 경우)
    watchlist_data = load_watchlist()
    all_watchlist = []
    for user_stocks in watchlist_data.get("users", {}).values():
        all_watchlist.extend(user_stocks)
    all_watchlist = list(set(all_watchlist))

    if all_watchlist:
        print(f"관심종목 분석 중: {all_watchlist}")
        watchlist_result = analyze_watchlist(all_watchlist, overseas, news)
        watchlist_message = format_watchlist_brief(watchlist_result, all_watchlist)
        message = message + "\n\n" + watchlist_message

    # 5. 성과 추적 — 오늘 추천 저장 + 과거 성과 평가
    brief_date = _now_kst().strftime("%Y-%m-%d")
    save_recommendations(analysis, brief_date)
    perf_summary = evaluate_and_update()
    if perf_summary:
        print(perf_summary)

    # 6. 카카오톡 발송
    print(f"메시지 총 길이: {len(message)}자")
    print("카카오톡 발송 중...")
    success = send_to_me(message)

    if success:
        print("모닝 브리핑 발송 완료!")
    else:
        print("발송 실패 — 메시지를 콘솔에 출력합니다:\n")
        print(message)

    return message


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--preview":
        # 카카오 발송 없이 콘솔 미리보기
        print("[미리보기 모드]\n")
        news = naver_news(20) + hankyung_news(15)
        overseas = fetch_overnight_summary()
        korean = fetch_korean_index()
        critical_error, warnings = validate_market_data(overseas, korean)
        for w in warnings:
            print(f"  {w}")
        if critical_error:
            raise ValueError("[데이터 검증 실패] 핵심 시장 데이터 이상 감지.\n" + "\n".join(warnings))
        analysis = analyze_morning_brief(overseas, korean, news)
        message = format_morning_brief(analysis, overseas, korean)
        sys.stdout.buffer.write((message + f"\n\n[문자 수: {len(message)}자]\n").encode("utf-8"))
    else:
        run_morning_brief()
