import os
import json
from datetime import datetime
from dotenv import load_dotenv

from scraper.naver_finance import fetch_market_news as naver_news, fetch_korean_index
from scraper.hankyung import fetch_market_news as hankyung_news
from scraper.yahoo_finance import fetch_overnight_summary
from analyzer.claude_analyzer import analyze_morning_brief, analyze_watchlist
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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 모닝 브리핑 시작")

    # 카카오 토큰 갱신 (access_token 6시간 만료 → 매 실행 시 refresh_token으로 재발급)
    tokens = refresh_access_token()
    if tokens.get("access_token"):
        os.environ["KAKAO_ACCESS_TOKEN"] = tokens["access_token"]

    # 1. 데이터 수집
    print("뉴스 수집 중...")
    news = naver_news(12) + hankyung_news(8)
    print(f"  → 총 {len(news)}건 수집")

    print("시장 데이터 수집 중...")
    overseas = fetch_overnight_summary()
    korean = fetch_korean_index()

    # 데이터 검증 (파싱 오류 감지: 0이거나 비정상적으로 낮은 경우만 차단)
    kospi_val = korean.get("코스피", {}).get("value", 0)
    if kospi_val and kospi_val < 500:
        raise ValueError(
            f"[데이터 검증 실패] 코스피 {kospi_val:,.2f}p — 비정상 저값 (파싱 오류 의심). 브리핑 중단."
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

    # 5. 카카오톡 발송
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
        kospi_val = korean.get("코스피", {}).get("value", 0)
        if kospi_val and kospi_val < 500:
            raise ValueError(f"[데이터 검증 실패] 코스피 {kospi_val:,.2f}p — 비정상 저값 (파싱 오류 의심).")
        analysis = analyze_morning_brief(overseas, korean, news)
        message = format_morning_brief(analysis, overseas, korean)
        sys.stdout.buffer.write((message + f"\n\n[문자 수: {len(message)}자]\n").encode("utf-8"))
    else:
        run_morning_brief()
