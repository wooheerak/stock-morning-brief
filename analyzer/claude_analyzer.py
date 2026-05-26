import json
import os
import time
from typing import List, Dict
from google import genai
from google.genai import errors as genai_errors
from dotenv import load_dotenv
from .prompts import MORNING_BRIEF_PROMPT, WATCHLIST_ANALYSIS_PROMPT, STOCK_QUERY_PROMPT

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 1순위 모델 → 503 반복 시 폴백 순서
_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
MODEL = _MODELS[0]

_MAX_RETRIES = 5          # 모델당 최대 재시도 횟수
_RETRY_BASE_SEC = 10      # 초기 대기 시간 (초), 이후 2배씩 증가


def _call_gemini(prompt: str) -> str:
    """503/429 등 일시적 오류에 대해 지수 백오프 + 모델 폴백으로 재시도"""
    last_exc: Exception = RuntimeError("Gemini 호출 실패")

    for model in _MODELS:
        wait = _RETRY_BASE_SEC
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = _client.models.generate_content(model=model, contents=prompt)
                if model != MODEL:
                    print(f"  [Gemini] 폴백 모델 사용: {model}")
                return response.text
            except genai_errors.ServerError as e:
                # 503 UNAVAILABLE — 일시적 과부하, 재시도 가능
                last_exc = e
                print(f"  [Gemini] {model} 503 오류 (시도 {attempt}/{_MAX_RETRIES}), {wait}초 대기...")
                time.sleep(wait)
                wait = min(wait * 2, 120)   # 최대 120초
            except genai_errors.ClientError as e:
                # 429 RESOURCE_EXHAUSTED — 할당량 초과, 잠시 대기 후 재시도
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    last_exc = e
                    print(f"  [Gemini] {model} 429 할당량 초과 (시도 {attempt}/{_MAX_RETRIES}), {wait}초 대기...")
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                else:
                    raise   # 4xx 기타 오류는 재시도 없이 즉시 올림
        print(f"  [Gemini] {model} {_MAX_RETRIES}회 재시도 소진 → 다음 모델로 폴백")

    raise RuntimeError(f"모든 Gemini 모델 호출 실패. 마지막 오류: {last_exc}") from last_exc


def _parse_json_response(text: str) -> Dict:
    # 마크다운 코드블록 제거
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("JSON 블록을 찾을 수 없습니다.")
    return json.loads(text[start:end])


def analyze_morning_brief(
    overseas_market: Dict,
    korean_market: Dict,
    news_list: List[Dict],
) -> Dict:
    """뉴스 + 시장 데이터 → 모닝 브리핑 분석"""
    overseas_str = _format_market_data(overseas_market)
    korean_str = _format_korean_market(korean_market)
    news_str = _format_news_list(news_list)

    bonds = overseas_market.get("bonds", {})
    bond_str = "\n".join(
        f"- {name}: {d.get('display', d.get('value', ''))} ({d['signal']}{d.get('change_bp', 0):+d}bp)"
        for name, d in bonds.items() if d
    ) or "데이터 없음"

    fx = overseas_market.get("fx", {})
    usdkrw_val = fx.get("달러/원", {}).get("value", 0)
    usdkrw_str = f"{usdkrw_val:,.0f}" if usdkrw_val else "데이터없음"

    prompt = MORNING_BRIEF_PROMPT.format(
        overseas_market=overseas_str,
        korean_market=korean_str,
        bond_data=bond_str,
        news_count=len(news_list),
        news_list=news_str,
        usdkrw=usdkrw_str,
    )

    response = _call_gemini(prompt)
    return _parse_json_response(response)


def analyze_watchlist(
    watchlist: List[str],
    market_data: Dict,
    news_list: List[Dict],
) -> Dict:
    """관심 종목 맞춤 분석"""
    related_news = [
        n for n in news_list
        if any(stock.replace(" ", "") in n["title"].replace(" ", "") for stock in watchlist)
    ]

    prompt = WATCHLIST_ANALYSIS_PROMPT.format(
        watchlist="\n".join(f"- {s}" for s in watchlist),
        market_data=_format_market_data(market_data),
        related_news=_format_news_list(related_news or news_list[:10]),
    )

    response = _call_gemini(prompt)
    return _parse_json_response(response)


def analyze_stock_query(
    stock_name: str,
    stock_code: str,
    news_list: List[Dict],
    market_context: Dict,
) -> str:
    """특정 종목 즉시 분석 (챗봇 응답용)"""
    related_news = [
        n for n in news_list
        if stock_name.replace(" ", "") in n["title"].replace(" ", "")
    ]

    prompt = STOCK_QUERY_PROMPT.format(
        stock_name=stock_name,
        stock_code=stock_code,
        news=_format_news_list(related_news[:5] if related_news else news_list[:5]),
        market_context=_format_market_data(market_context),
    )

    return _call_gemini(prompt)


def _format_market_data(data: Dict) -> str:
    lines = []
    for category, items in data.items():
        if isinstance(items, dict) and "value" in items:
            d = items
            lines.append(f"- {category}: {d['signal']} {d['change_pct']:+.2f}%")
        elif isinstance(items, dict):
            for name, d in items.items():
                if isinstance(d, dict) and "change_pct" in d:
                    lines.append(f"- {name}: {d['signal']} {d['change_pct']:+.2f}%")
    return "\n".join(lines) if lines else "데이터 없음"


def _format_korean_market(data: Dict) -> str:
    lines = []
    for name, d in data.items():
        if isinstance(d, dict) and "change_pct" in d:
            lines.append(f"- {name}: {d['value']:,.2f} ({d['signal']} {d['change_pct']:+.2f}%)")
    return "\n".join(lines) if lines else "데이터 없음"


def _format_news_list(news_list: List[Dict]) -> str:
    lines = []
    for i, n in enumerate(news_list):
        source = n.get("source", "")
        time = n.get("time", "")
        source_time = f"{source} {time}".strip() if time else source
        lines.append(f"{i+1}. [{source_time}] {n['title']}")
    return "\n".join(lines)
