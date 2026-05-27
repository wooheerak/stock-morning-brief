from datetime import datetime, timezone, timedelta
import re
from typing import Dict, List

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    """타임존에 무관하게 항상 KST 기준 현재 시각 반환"""
    return datetime.now(KST).replace(tzinfo=None)

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
CATEGORY_LABEL = {
    "구조적성장": "구조적성장",
    "이벤트드리븐": "이벤트",
    "수주기반": "수주기반",
    "가치": "가치",
}
SIGNAL_EMOJI = {"추격가능": "🟢", "눌림목대기": "🟡", "관망": "🔴"}


def _norm_dt(time_str: str, today: datetime) -> str:
    if not time_str:
        return ""
    if re.match(r'\d{4}/\d{2}/\d{2}', time_str):
        return time_str
    if re.match(r'^\d{2}:\d{2}$', time_str.strip()):
        return today.strftime("%Y/%m/%d ") + time_str.strip()
    return time_str


def _cut(text: str, limit: int) -> str:
    return text[:limit] + "…" if len(text) > limit else text


def _fmt_date(time_str: str) -> str:
    """YYYY/MM/DD HH:MM → YYYY년 MM월 DD일 HH:MM"""
    m = re.match(r'(\d{4})/(\d{2})/(\d{2})\s+(\d{2}:\d{2})', time_str)
    if m:
        return f"{m.group(1)}년 {m.group(2)}월 {m.group(3)}일 {m.group(4)}"
    m2 = re.match(r'(\d{4})/(\d{2})/(\d{2})', time_str)
    if m2:
        return f"{m2.group(1)}년 {m2.group(2)}월 {m2.group(3)}일"
    return time_str


def _data_reliability_score(val_warnings: list) -> int:
    """검증 경고 수 → 데이터 신뢰도 점수 (0~100)."""
    score = 100
    for w in val_warnings:
        if "수집 실패" in w:
            score -= 5
        elif "비정상 값" in w or "파싱 오류" in w:
            score -= 15
        elif "불일치" in w:
            score -= 8
    return max(0, min(100, score))


def format_morning_brief(
    analysis: Dict,
    overseas: Dict,
    korean_market: Dict,
    date: datetime = None,
    val_warnings: list = None,
) -> str:
    if date is None:
        date = _now_kst()

    weekday = WEEKDAY_KR[date.weekday()]
    date_str = date.strftime(f"%Y.%m.%d ({weekday})")
    fetch_time = overseas.get("fetched_at", date.strftime("%Y/%m/%d %H:%M"))

    sentiment = analysis.get("market_sentiment", "중립")
    score = analysis.get("sentiment_score", 50)
    breakdown = analysis.get("sentiment_breakdown", "")
    s_emoji = {"긍정": "🟢", "중립": "🟡", "부정": "🔴"}.get(sentiment, "🟡")

    lines = [f"📊 {date_str} 모닝 브리핑", ""]

    # 1분 요약 (비전문가용)
    qs = analysis.get("quick_summary", {})
    if qs:
        mood_map = {"긍정": "주목", "중립": "관망", "부정": "조심"}
        mood = mood_map.get(sentiment, "관망")
        lines.append("━━ 1분 요약 ━━")
        lines.append(f"{s_emoji} {mood}")
        if qs.get("one_line"):
            lines.append(_cut(qs["one_line"], 85))
        if qs.get("action"):
            lines.append(f"전략: {_cut(qs['action'], 80)}")
        checks = qs.get("check_top3", [])
        if checks:
            nums = ["①", "②", "③"]
            for i, c in enumerate(checks[:3]):
                lines.append(f"  {nums[i]} {_cut(c, 32)}")
        lines.append("─" * 18)
        lines.append("")

    # 시장심리 + 산식
    lines.append(f"시장심리: {s_emoji} {sentiment} {score}점")
    if breakdown:
        lines.append(f"  └ {_cut(breakdown, 110)}")

    # 시장 스타일
    market_style = analysis.get("market_style", [])
    if market_style:
        lines.append("📌 " + " | ".join(market_style[:3]))
    lines.append("")

    # 해외 지수
    indices = overseas.get("indices", {})
    if indices:
        parts = [f"{n} {d['signal']}{d['change_pct']:+.1f}%" for n, d in indices.items() if d]
        lines.append("🌏 해외지수 (전일 미국장 마감)")
        lines.append("  " + " | ".join(parts))

    # 미국채 금리
    bonds = overseas.get("bonds", {})
    tnx = bonds.get("미국채10년물")
    if tnx:
        bp = tnx.get("change_bp", 0)
        lines.append(f"  🏦 미국채10년물 {tnx['value']:.2f}% {tnx['signal']}{bp:+d}bp")

    # 주요 미국 종목
    stocks = overseas.get("stocks", {})
    if stocks:
        parts = [f"{n} {d['signal']}{d['change_pct']:+.1f}%" for n, d in stocks.items() if d]
        lines.append("  " + " | ".join(parts))

    # 환율
    fx = overseas.get("fx", {})
    fx_parts = []
    if fx.get("달러/원"):
        d = fx["달러/원"]
        fx_parts.append(f"달러/원 {d['value']:,.1f}원 {d['signal']}{d['change_pct']:+.1f}%")
    if fx.get("달러/엔"):
        d = fx["달러/엔"]
        fx_parts.append(f"달러/엔 {d['value']:.1f} {d['signal']}{d['change_pct']:+.1f}%")
    if fx_parts:
        lines.append("  💱 " + " | ".join(fx_parts))

    # 원자재
    commodities = overseas.get("commodities", {})
    if commodities:
        comm_parts = []
        for name, d in commodities.items():
            if d and "change_pct" in d:
                comm_parts.append(f"{name} {d['signal']}{d['change_pct']:+.1f}%")
        if comm_parts:
            lines.append("  🛢️ " + " | ".join(comm_parts))

    # 투자자별 수급
    investor_trend = overseas.get("investor_trend", {})
    if investor_trend:
        trend_parts = []
        for market, d in investor_trend.items():
            if not isinstance(d, dict):
                continue
            f_val = d.get("foreigner", 0)
            i_val = d.get("institution", 0)
            f_sig = "▲" if f_val > 0 else "▼" if f_val < 0 else "━"
            i_sig = "▲" if i_val > 0 else "▼" if i_val < 0 else "━"
            trend_parts.append(
                f"{market} 외국인{f_sig}{f_val:+,d}억 기관{i_sig}{i_val:+,d}억"
            )
        if trend_parts:
            lines.append("  👥 전일수급 " + " | ".join(trend_parts))

    # 국내 지수 — 장중/전일종가 동적 라벨
    if korean_market:
        # 메타 키(_로 시작) 제외하고 지수 데이터만 추출
        parts = [
            f"{n} {d['value']:,.2f}p {d['signal']}{d['change_pct']:+.2f}%"
            for n, d in korean_market.items()
            if isinstance(d, dict) and "value" in d
        ]
        kr_fetch = korean_market.get("_fetched_at", fetch_time)
        is_intraday = korean_market.get("_is_intraday", False)
        kr_label = f"장중, {kr_fetch}" if is_intraday else f"전일 마감, 수집: {kr_fetch}"
        lines.append(f"🇰🇷 국내지수 ({kr_label})")
        lines.append("  " + " | ".join(parts))
    # 강한/약한 섹터
    strong = analysis.get("strong_sectors", [])
    weak = analysis.get("weak_sectors", [])
    if strong or weak:
        s_str = "🔥 " + "·".join(_cut(s, 10) for s in strong[:3]) if strong else ""
        w_str = "❄️ " + "·".join(_cut(w, 10) for w in weak[:3]) if weak else ""
        lines.append("  ".join(filter(None, [s_str, w_str])))
    lines.append("")

    # 핵심 이슈 (수치 + 투자 시사점)
    key_issues = analysis.get("key_issues", [])
    if key_issues:
        lines.append("📰 핵심 이슈")
        for i, issue in enumerate(key_issues[:2], 1):
            title = issue.get("title", "")
            summary = issue.get("summary", "")
            implication = issue.get("implication", "")
            source = issue.get("source", "")
            t = _norm_dt(issue.get("time", ""), date)
            meta = f"{source} {t}".strip() if t else source

            lines.append(f"{i}. {title}")
            if summary:
                lines.append(f"   └ {_cut(summary, 80)}")
            if implication:
                lines.append(f"   → {_cut(implication, 70)}")
            if source:
                # source 필드에 날짜가 섞여 들어온 경우 제거 (예: "한국경제 2026/05/12 10:41" → "한국경제")
                clean_source = re.sub(r'\s+\d{4}[/\-]\d{2}[/\-]\d{2}.*$', '', source).strip()
                date_str = _fmt_date(t) if t else ""
                source_line = f"{clean_source} · {date_str}" if date_str else clean_source
                lines.append(f"   출처: {source_line}")
        lines.append("")

    # 단기 주목 종목
    short_stocks = analysis.get("short_term_stocks", [])
    if short_stocks:
        lines.append("⚡ 단기 주목 (1~5일)")
        for s in short_stocks[:2]:
            sig = s.get("trade_signal", "")
            sig_emoji = SIGNAL_EMOJI.get(sig, "")
            prev = s.get("prev_change", "")
            lines.append(f"• {s['name']}({s['code']}) {prev}  {sig_emoji}{sig}")
            if s.get("action_guide"):
                lines.append(f"  전략: {_cut(s['action_guide'], 60)}")
            lines.append(f"  근거: {_cut(s['reason'], 60)}")
            if s.get("stop_loss"):
                lines.append(f"  손절: {s['stop_loss']}")
            lines.append(f"  ⚠️ {_cut(s['risk'], 48)}")
        lines.append("")

    # 중기 관심 종목
    mid_stocks = analysis.get("mid_term_stocks", [])
    if mid_stocks:
        lines.append("📈 중기 관심 (1~3개월)")
        for s in mid_stocks[:3]:
            cat = CATEGORY_LABEL.get(s.get("category", ""), s.get("category", ""))
            lines.append(f"• [{cat}] {s['name']}({s['code']})")
            lines.append(f"  {_cut(s['reason'], 60)}")
        lines.append("")

    # 오늘 전략 + 스탠스
    strategy = analysis.get("today_strategy", "")
    stance = analysis.get("strategy_stance", {})
    if strategy or stance:
        lines.append("💡 오늘 전략")
        if stance:
            stance_label = f"{stance.get('emoji', '')} {stance.get('label', '')} | 현금 {stance.get('cash_ratio', '')}"
            lines.append(f"  📌 {stance_label}")
        if strategy:
            lines.append(f"  {_cut(strategy, 110)}")
        lines.append("")

    # 리스크
    risks = analysis.get("risk_factors", [])
    if risks:
        lines.append("⚠️ 리스크")
        for r in risks[:3]:
            lines.append(f"  • {_cut(r, 60)}")
        lines.append("")

    # 오늘 체크포인트
    checkpoints = analysis.get("checkpoints", [])
    if checkpoints:
        lines.append("👀 오늘 체크포인트")
        for c in checkpoints[:5]:
            lines.append(f"  □ {_cut(c, 48)}")
        lines.append("")

    # 데이터 신뢰도 + 가드레일 상태 footer
    if val_warnings is None:
        val_warnings = []
    reliability = _data_reliability_score(val_warnings)
    fail_items = [re.sub(r'^[\W\s]+', '', w.split(":")[0]).strip() for w in val_warnings]
    fail_str = "(" + ", ".join(f[:8] for f in fail_items[:2]) + " 실패)" if fail_items else ""

    guardrail_log = analysis.get("_guardrail_log", [])
    guardrail_str = "적용" if guardrail_log else "미적용"

    is_intraday = korean_market.get("_is_intraday", False)
    news_label = "장중" if is_intraday else "36h이내"

    lines.append(
        f"[데이터 {reliability}점{fail_str} | 뉴스 {news_label} | 전략보정 {guardrail_str}]"
    )
    lines.append("※ 투자 판단은 본인 결정 하에 진행하세요.")
    return "\n".join(lines)


def format_watchlist_brief(watchlist_analysis: Dict, watchlist: List[str]) -> str:
    lines = ["📌 관심종목 분석", ""]

    for item in watchlist_analysis.get("watchlist_analysis", []):
        outlook_emoji = {"긍정": "🟢", "중립": "🟡", "부정": "🔴"}.get(
            item.get("today_outlook", "중립"), "🟡"
        )
        action_emoji = {"매수검토": "📈", "관망": "👀", "주의": "⚠️"}.get(
            item.get("action_hint", "관망"), "👀"
        )
        lines.append(f"{outlook_emoji} {item['name']}({item['code']}) {action_emoji} {item['action_hint']}")
        if item.get("key_news"):
            lines.append(f"  뉴스: {_cut(item['key_news'], 45)}")
        lines.append(f"  {_cut(item['reason'], 50)}")
        if item.get("watch_point"):
            lines.append(f"  주시: {_cut(item['watch_point'], 40)}")

    lines.append("")
    lines.append("※ 투자 판단은 본인 결정 하에 진행하세요.")
    return "\n".join(lines)
