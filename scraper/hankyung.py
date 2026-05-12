import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

KST = timezone(timedelta(hours=9))

RSS_SOURCES = [
    ("https://www.hankyung.com/feed/finance", "한국경제"),
    ("https://www.hankyung.com/feed/economy", "한국경제(경제)"),
    ("https://www.mk.co.kr/rss/30100041/", "매일경제"),
]


def _parse_pub_date(pub_date_str: str) -> str:
    """pubDate 문자열 → 'YYYY/MM/DD HH:MM' 형식"""
    try:
        dt = parsedate_to_datetime(pub_date_str)
        dt_kst = dt.astimezone(KST)
        return dt_kst.strftime("%Y/%m/%d %H:%M")
    except Exception:
        return ""


def fetch_market_news(count: int = 15) -> List[Dict]:
    """RSS 피드로 주요 경제/증권 뉴스 수집 (시간 포함)"""
    articles = []
    seen = set()

    for rss_url, source_name in RSS_SOURCES:
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "xml")

            for item in soup.select("item"):
                title_tag = item.find("title")
                link_tag = item.find("link")
                pub_tag = item.find("pubDate")

                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                link = link_tag.get_text(strip=True) if link_tag else ""
                pub_time = _parse_pub_date(pub_tag.get_text(strip=True)) if pub_tag else ""

                if title and title not in seen and len(title) > 5:
                    seen.add(title)
                    articles.append({
                        "title": title,
                        "url": link,
                        "source": source_name,
                        "time": pub_time,
                    })

        except Exception as e:
            print(f"[{source_name}] RSS 수집 실패: {e}")

        if len(articles) >= count:
            break

    return articles[:count]


if __name__ == "__main__":
    news = fetch_market_news(5)
    for n in news:
        print(f"[{n['source']} {n['time']}] {n['title']}")
