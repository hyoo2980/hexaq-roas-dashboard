from datetime import date

import requests

from collectors.cafe24 import _is_target_item as _is_target_cafe24_item
from collectors.cafe24 import fetch_orders as fetch_cafe24_orders
from collectors.coupang import _is_target_item as _is_target_coupang_item
from collectors.coupang import fetch_ordersheets
from config import DISCORD_WEBHOOK_URL_ORDERS
from storage.db import (
    filter_unnotified_order_ids,
    get_today_cumulative_amount,
    init_db,
    mark_order_notified,
)

COLOR_BY_PLATFORM = {
    "cafe24": 0x1E88E5,
    "coupang": 0xE53935,
}
EMOJI_BY_PLATFORM = {
    "cafe24": "🛍️",
    "coupang": "📦",
}
LABEL_BY_PLATFORM = {
    "cafe24": "자사몰(카페24)",
    "coupang": "쿠팡",
}


def _send_order_alert(platform: str, order_id: str, amount: float, cumulative_today: float, detail: str = ""):
    embed = {
        "title": f"{EMOJI_BY_PLATFORM[platform]} 새 주문 — {LABEL_BY_PLATFORM[platform]}",
        "color": COLOR_BY_PLATFORM[platform],
        "fields": [
            {"name": "주문번호", "value": str(order_id), "inline": True},
            {"name": "금액", "value": f"{amount:,.0f}원", "inline": True},
            {"name": "오늘 누적 결제금액", "value": f"{cumulative_today:,.0f}원", "inline": True},
        ],
    }
    if detail:
        embed["fields"].append({"name": "상세", "value": detail, "inline": False})
    resp = requests.post(DISCORD_WEBHOOK_URL_ORDERS, json={"embeds": [embed]}, timeout=30)
    resp.raise_for_status()


def _is_pure_target_order_cafe24(o: dict) -> bool:
    items = o.get("items", [])
    target_items = [i for i in items if _is_target_cafe24_item(i)]
    return bool(target_items) and len(target_items) == len(items)


def _is_pure_target_order_coupang(o: dict) -> bool:
    items = o.get("orderItems", [])
    target_items = [i for i in items if _is_target_coupang_item(i)]
    return bool(target_items) and len(target_items) == len(items)


def _cafe24_amount(o: dict) -> float:
    return float(o["actual_order_amount"].get("payment_amount", 0))


def _coupang_amount(o: dict) -> float:
    target_items = [i for i in o.get("orderItems", []) if _is_target_coupang_item(i)]
    amount = sum(float(i.get("salesPrice", 0)) * int(i.get("shippingCount", 1)) for i in target_items)
    amount += float(o.get("shippingPrice", 0))
    return amount


def check_cafe24_new_orders(today: str):
    orders = fetch_cafe24_orders(today)
    target_orders = [o for o in orders if _is_pure_target_order_cafe24(o)]
    order_ids = [o["order_id"] for o in target_orders]
    new_ids = set(filter_unnotified_order_ids("cafe24", order_ids))
    if not new_ids:
        return 0
    for o in target_orders:
        if o["order_id"] not in new_ids:
            continue
        amount = _cafe24_amount(o)
        target_items = [i for i in o.get("items", []) if _is_target_cafe24_item(i)]
        names = ", ".join(i.get("product_name", "") for i in target_items)
        cumulative = get_today_cumulative_amount(today) + amount
        _send_order_alert("cafe24", o["order_id"], amount, cumulative, detail=names)
        mark_order_notified("cafe24", o["order_id"], amount)
    return len(new_ids)


def check_coupang_new_orders(today: str):
    orders = fetch_ordersheets(today)
    target_orders = [o for o in orders if _is_pure_target_order_coupang(o)]
    order_ids = [str(o["orderId"]) for o in target_orders]
    new_ids = set(filter_unnotified_order_ids("coupang", order_ids))
    if not new_ids:
        return 0
    for o in target_orders:
        oid = str(o["orderId"])
        if oid not in new_ids:
            continue
        amount = _coupang_amount(o)
        target_items = [i for i in o.get("orderItems", []) if _is_target_coupang_item(i)]
        names = ", ".join(i.get("sellerProductName", "") for i in target_items)
        cumulative = get_today_cumulative_amount(today) + amount
        _send_order_alert("coupang", oid, amount, cumulative, detail=names)
        mark_order_notified("coupang", oid, amount)
    return len(new_ids)


def bootstrap_seen_orders():
    """Marks all of today's existing orders as already-notified (with their
    amounts, so the running cumulative total is accurate from the first real
    alert) WITHOUT sending alerts. Run this once before starting the watch loop
    so the first poll doesn't dump every order placed earlier today."""
    init_db()
    today = date.today().isoformat()

    cafe24_orders = fetch_cafe24_orders(today)
    cafe24_count = 0
    for o in cafe24_orders:
        if _is_pure_target_order_cafe24(o):
            mark_order_notified("cafe24", o["order_id"], _cafe24_amount(o))
            cafe24_count += 1

    coupang_orders = fetch_ordersheets(today)
    coupang_count = 0
    for o in coupang_orders:
        if _is_pure_target_order_coupang(o):
            mark_order_notified("coupang", str(o["orderId"]), _coupang_amount(o))
            coupang_count += 1

    print(f"부트스트랩 완료: cafe24={cafe24_count} coupang={coupang_count}건을 기존 주문으로 기록")


def check_all_new_orders():
    """Single poll pass across both channels for today's orders. Safe to call
    repeatedly -- already-notified order IDs are skipped via the notified_orders table."""
    init_db()
    today = date.today().isoformat()
    counts = {}
    for platform, fn in (
        ("cafe24", check_cafe24_new_orders),
        ("coupang", check_coupang_new_orders),
    ):
        try:
            counts[platform] = fn(today)
        except Exception:
            import traceback

            counts[platform] = "ERROR: " + traceback.format_exc()
    return counts
