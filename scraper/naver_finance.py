import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import re

_KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 네이버 금융 RSS (시간 포함)
NAVER_FINANCE_RSS = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"

# 네이버 모바일 지수 API (코스피/코스닥 가격지수 — yfinance ^KS11은 TR지수라 수치 오류)
_NAVER_INDEX_API = "https://m.stock.naver.com/api/index/{code}/basic"
_KR_INDICES = {"코스피": "KOSPI", "코스닥": "KOSDAQ"}


def fetch_korean_index() -> Dict:
    """네이버 모바일 API로 코스피/코스닥 전일 마감 데이터 수집"""
    result = {}
    for name, code in _KR_INDICES.items():
        try:
            url = _NAVER_INDEX_API.format(code=code)
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            close = float(data["closePrice"].replace(",", ""))
            change_pct = float(data["fluctuationsRatio"].replace(",", ""))
            change = float(data["compareToPreviousClosePrice"].replace(",", ""))

            result[name] = {
                "value": close,
                "change_pct": change_pct,
                "signal": "▲" if change > 0 else "▼" if change < 0 else "━",
            }
        except Exception as e:
            print(f"[네이버 지수] {name} 실패: {e}")
    return result


def fetch_market_news(count: int = 20) -> List[Dict]:
    """네이버 금융 주요 뉴스 수집 (시간 포함)"""
    url = NAVER_FINANCE_RSS
    articles = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # 제목과 날짜 함께 추출
        news_dl = soup.select("dl.newsList, dl")
        seen = set()

        for dl in news_dl:
            subject = dl.select_one(".articleSubject a")
            date_dd = dl.select_one(".articleDate, dd.articleDate")

            if not subject:
                continue

            title = subject.get_text(strip=True)
            href = subject.get("href", "")

            if not title or title in seen:
                continue
            seen.add(title)

            link = ("https://finance.naver.com" + href) if not href.startswith("http") else href

            # 시간 추출 (형식: 2026.05.12 11:23 or 11:23)
            time_str = ""
            if date_dd:
                raw = date_dd.get_text(strip=True)
                # YYYY.MM.DD HH:MM 패턴
                m = re.search(r'(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}:\d{2})', raw)
                if m:
                    time_str = f"{m.group(1)}/{m.group(2)}/{m.group(3)} {m.group(4)}"
                else:
                    # HH:MM 만 있는 경우 오늘 날짜 붙이기 (KST 기준)
                    m2 = re.search(r'(\d{2}:\d{2})', raw)
                    if m2:
                        today = datetime.now(_KST).strftime("%Y/%m/%d")
                        time_str = f"{today} {m2.group(1)}"

            articles.append({
                "title": title,
                "url": link,
                "source": "네이버금융",
                "time": time_str,
            })

            if len(articles) >= count:
                break

        # dl 구조가 없을 경우 fallback
        if not articles:
            for item in soup.select(".articleSubject a")[:count]:
                title = item.get_text(strip=True)
                href = item.get("href", "")
                if title and title not in seen:
                    seen.add(title)
                    link = ("https://finance.naver.com" + href) if not href.startswith("http") else href
                    articles.append({"title": title, "url": link, "source": "네이버금융", "time": ""})

    except Exception as e:
        print(f"[네이버금융] 수집 실패: {e}")

    return articles


def fetch_article_content(url: str) -> str:
    """개별 기사 본문 수집"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        content_div = soup.select_one("div#newsct_article") or soup.select_one("div.articleCont")
        if content_div:
            return content_div.get_text(separator=" ", strip=True)[:2000]
    except Exception:
        pass
    return ""


def fetch_sector_news(sector_code: str = "005", count: int = 10) -> List[Dict]:
    """섹터별 뉴스 수집"""
    url = f"https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3={sector_code}"
    articles = []
    seen = set()

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        for item in soup.select(".articleSubject a")[:count]:
            title = item.get_text(strip=True)
            href = item.get("href", "")
            if title and title not in seen:
                seen.add(title)
                link = ("https://finance.naver.com" + href) if not href.startswith("http") else href
                articles.append({"title": title, "url": link, "source": "네이버금융(섹터)", "time": ""})
    except Exception as e:
        print(f"[네이버금융 섹터] 수집 실패: {e}")

    return articles


if __name__ == "__main__":
    news = fetch_market_news(5)
    for n in news:
        print(f"[{n['source']} {n['time']}] {n['title']}")
