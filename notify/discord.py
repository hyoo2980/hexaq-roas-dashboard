from datetime import date, timedelta

import requests

from analysis.metrics import shorten_adset_name as _shorten_adset_name
from analysis.roas import brand_total_roas, daily_roas_by_adset, latest_change_summary, load_adset_df
from config import DISCORD_WEBHOOK_URL


def _fmt_pct(x):
    if x is None or x != x:  # NaN check
        return "-"
    return f"{x * 100:+.1f}%"


def _fmt_roas(x):
    if x is None or x != x:
        return "-"
    return f"{x:.2f}"


def _fmt_roas_breakdown(roas, revenue, spend, net_profit=None):
    """e.g. "2.07 (1,037,400/500,032) | 순이익(추정) +135,936원" """
    if roas is None or roas != roas:
        return "-"
    base = f"{roas:.2f} ({revenue:,.0f}/{spend:,.0f})"
    if net_profit is not None and net_profit == net_profit:
        base += f" | 순이익(추정) {net_profit:+,.0f}원"
    return base


def _period_label(start_str: str, end_str: str, days: int) -> str:
    return f"최근 {days}일 누적 브랜드 ROAS ({start_str} ~ {end_str})"


def build_report(report_date: str) -> dict:
    target = date.fromisoformat(report_date)
    week_start = (target - timedelta(days=6)).isoformat()
    twoweek_start = (target - timedelta(days=13)).isoformat()
    month_start = (target - timedelta(days=29)).isoformat()

    df = load_adset_df(week_start, report_date)
    daily = daily_roas_by_adset(df)
    changes = latest_change_summary(daily)
    brand_today = brand_total_roas(report_date, report_date)
    brand_week = brand_total_roas(week_start, report_date)
    brand_2week = brand_total_roas(twoweek_start, report_date)
    brand_month = brand_total_roas(month_start, report_date)

    fields = []

    fields.append(
        {
            "name": f"📊 브랜드 전체 ROAS ({report_date})",
            "value": (
                f"광고비 총액: {brand_today['total_spend']:,.0f}원\n"
                f"자사몰(카페24) 매출: {brand_today['own_store_value']:,.0f}원\n"
                f"쿠팡 매출: {brand_today['coupang_value']:,.0f}원\n"
                f"브랜드 종합 ROAS(추정): {_fmt_roas_breakdown(brand_today['brand_total_roas'], brand_today['total_value'], brand_today['total_spend'], brand_today['brand_net_profit'])}"
            ),
            "inline": False,
        }
    )

    for label_days, start_str, brand in (
        (7, week_start, brand_week),
        (14, twoweek_start, brand_2week),
        (30, month_start, brand_month),
    ):
        fields.append(
            {
                "name": f"📅 {_period_label(start_str, report_date, label_days)}",
                "value": (
                    f"광고비 총액: {brand['total_spend']:,.0f}원\n"
                    f"자사몰 매출: {brand['own_store_value']:,.0f}원 | 쿠팡 매출: {brand['coupang_value']:,.0f}원\n"
                    f"종합 ROAS(추정): {_fmt_roas_breakdown(brand['brand_total_roas'], brand['total_value'], brand['total_spend'], brand['brand_net_profit'])}"
                ),
                "inline": False,
            }
        )

    if not changes.empty:
        top = changes.sort_values("spend", ascending=False).head(5)
        lines = []
        for _, r in top.iterrows():
            lines.append(
                f"**{_shorten_adset_name(r['adset_name'])}**\n"
                f"ROAS {_fmt_roas(r['roas'])} | 1일 {_fmt_pct(r['roas_change_1d'])} · "
                f"3일 {_fmt_pct(r['roas_change_3d'])} · 5일 {_fmt_pct(r['roas_change_5d'])}"
            )
        fields.append(
            {
                "name": "📈 광고세트별 ROAS 변동 (광고비 상위 5개)",
                "value": "\n\n".join(lines)[:1000],
                "inline": False,
            }
        )

    embed = {
        "title": f"ROAS 일일 리포트 — {report_date}",
        "color": 0x5865F2,
        "fields": fields,
    }
    return {"embeds": [embed]}


def send_daily_report(report_date: str):
    payload = build_report(report_date)
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=30)
    resp.raise_for_status()
