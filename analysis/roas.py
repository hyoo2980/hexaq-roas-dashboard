from datetime import date

import numpy as np
import pandas as pd

from analysis.fx import get_usd_krw_rate
from config import BEP_ROAS
from storage.db import (
    fetch_cafe24_daily,
    fetch_cafe24_refund_daily,
    fetch_coupang_daily,
    fetch_meta_adset_daily,
)


def load_adset_df(start_date: str, end_date: str) -> pd.DataFrame:
    """Loads Meta adset daily data across all configured ad accounts and converts
    USD spend/purchase_value to KRW. Each ad account can have its own reporting
    currency -- conversion is applied per-row based on that row's currency."""
    rows = fetch_meta_adset_daily(start_date, end_date)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])

    fx_rate = get_usd_krw_rate()
    is_usd = df["currency"] == "USD"
    df.loc[is_usd, "spend"] = df.loc[is_usd, "spend"] * fx_rate
    df.loc[is_usd, "purchase_value"] = df.loc[is_usd, "purchase_value"] * fx_rate

    df["roas"] = df["purchase_value"] / df["spend"].replace(0, np.nan)
    df["ctr"] = df["clicks"] / df["impressions"].replace(0, np.nan)
    df["lpv_rate"] = df["landing_page_views"] / df["link_clicks"].replace(0, np.nan)
    df["cvr"] = df["purchases"] / df["landing_page_views"].replace(0, np.nan)
    return df


def daily_roas_by_adset(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    agg = (
        df.groupby(["date", "adset_id", "adset_name"])
        .agg(spend=("spend", "sum"), purchase_value=("purchase_value", "sum"))
        .reset_index()
    )
    agg["roas"] = agg["purchase_value"] / agg["spend"].replace(0, np.nan)
    return agg.sort_values(["adset_id", "date"])


def change_rates(daily_df: pd.DataFrame, periods=(1, 3, 5)) -> pd.DataFrame:
    """daily_df: output of daily_roas_by_adset. Adds N-day change columns per adset."""
    if daily_df.empty:
        return daily_df
    out = daily_df.copy()
    out = out.sort_values(["adset_id", "date"])
    for p in periods:
        out[f"roas_change_{p}d"] = out.groupby("adset_id")["roas"].pct_change(periods=p)
        out[f"spend_change_{p}d"] = out.groupby("adset_id")["spend"].pct_change(periods=p)
    return out


def latest_change_summary(daily_df: pd.DataFrame, periods=(1, 3, 5)) -> pd.DataFrame:
    """Returns the most recent row per adset with its N-day change rates."""
    changed = change_rates(daily_df, periods)
    if changed.empty:
        return changed
    latest = changed.sort_values("date").groupby("adset_id").tail(1)
    return latest.reset_index(drop=True)


def spend_by_account(df: pd.DataFrame) -> pd.DataFrame:
    """Per Meta ad-account spend breakdown (KRW, after currency conversion)."""
    if df.empty:
        return df
    agg = (
        df.groupby(["ad_account_id", "ad_account_name"])
        .agg(spend=("spend", "sum"))
        .reset_index()
        .sort_values("spend", ascending=False)
    )
    return agg


def account_roas_summary(df: pd.DataFrame, active_adset_ids: set) -> list:
    """For each Meta ad account: account-wide ROAS plus a per-adset ROAS breakdown
    restricted to currently ACTIVE adsets."""
    if df.empty:
        return []

    results = []
    for account_id, acc_df in df.groupby("ad_account_id"):
        account_name = acc_df["ad_account_name"].iloc[0]
        acc_spend = acc_df["spend"].sum()
        acc_value = acc_df["purchase_value"].sum()
        acc_roas = (acc_value / acc_spend) if acc_spend else None

        active_df = acc_df[acc_df["adset_id"].isin(active_adset_ids)]
        adset_agg = (
            active_df.groupby(["adset_id", "adset_name"])
            .agg(
                spend=("spend", "sum"),
                purchase_value=("purchase_value", "sum"),
                impressions=("impressions", "sum"),
                clicks=("clicks", "sum"),
                landing_page_views=("landing_page_views", "sum"),
                purchases=("purchases", "sum"),
            )
            .reset_index()
        )
        adset_agg["roas"] = adset_agg["purchase_value"] / adset_agg["spend"].replace(0, np.nan)
        adset_agg["ctr"] = adset_agg["clicks"] / adset_agg["impressions"].replace(0, np.nan)
        adset_agg["cvr"] = adset_agg["purchases"] / adset_agg["landing_page_views"].replace(0, np.nan)

        results.append(
            {
                "ad_account_id": account_id,
                "ad_account_name": account_name,
                "account_spend": acc_spend,
                "account_value": acc_value,
                "account_roas": acc_roas,
                "active_adsets": adset_agg.sort_values("spend", ascending=False).to_dict("records"),
            }
        )
    return sorted(results, key=lambda r: r["account_spend"], reverse=True)


def brand_total_roas(start_date: str, end_date: str) -> dict:
    """Brand-level ROAS: Meta ad spend vs. Cafe24 own-store revenue + Coupang
    revenue (actual sales from each channel's own order API, not Meta's
    pixel-attributed purchase value)."""
    adset_df = load_adset_df(start_date, end_date)
    total_spend = adset_df["spend"].sum() if not adset_df.empty else 0

    cafe24_rows = fetch_cafe24_daily(start_date, end_date)
    cafe24_refund_total = sum(
        r["refund_amount"] for r in fetch_cafe24_refund_daily(start_date, end_date)
    )
    own_store_value = sum(r["sales_amount"] for r in cafe24_rows) - cafe24_refund_total

    coupang_rows = fetch_coupang_daily(start_date, end_date)
    coupang_value = sum(r["sales_amount"] for r in coupang_rows)

    total_value = own_store_value + coupang_value
    own_store_roas = (own_store_value / total_spend) if total_spend else None
    brand_roas = (total_value / total_spend) if total_spend else None

    return {
        "total_spend": total_spend,
        "own_store_value": own_store_value,
        "coupang_value": coupang_value,
        "total_value": total_value,
        "own_store_roas": own_store_roas,
        "brand_total_roas": brand_roas,
        "own_store_net_profit": estimate_net_profit(own_store_value, total_spend),
        "brand_net_profit": estimate_net_profit(total_value, total_spend),
    }


def estimate_net_profit(revenue: float, spend: float) -> float | None:
    """Estimated net profit using the break-even ROAS (BEP_ROAS):
    profit = revenue/BEP_ROAS - spend. Returns None if BEP_ROAS isn't configured."""
    if not spend or BEP_ROAS is None:
        return None
    return revenue / BEP_ROAS - spend
