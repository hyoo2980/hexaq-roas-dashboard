import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from config import COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY, COUPANG_TARGET_KEYWORD, COUPANG_VENDOR_ID

BASE_URL = "https://api-gateway.coupang.com"


def _signed_date():
    return datetime.now(timezone.utc).strftime("%y%m%d") + "T" + datetime.now(timezone.utc).strftime("%H%M%S") + "Z"


def _sign(method: str, path: str, query: str):
    signed_date = _signed_date()
    message = signed_date + method + path + query
    signature = hmac.new(
        COUPANG_SECRET_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return signed_date, signature


def _request(method: str, path: str, params: dict | None = None):
    params = params or {}
    query = urlencode(params)
    signed_date, signature = _sign(method, path, query)

    authorization = (
        f"CEA algorithm=HmacSHA256, access-key={COUPANG_ACCESS_KEY}, "
        f"signed-date={signed_date}, signature={signature}"
    )
    headers = {"Authorization": authorization, "Content-Type": "application/json"}

    url = f"{BASE_URL}{path}"
    resp = requests.request(method, url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


ACTIVE_STATUSES = ["ACCEPT", "INSTRUCT", "DEPARTURE", "DELIVERING", "FINAL_DELIVERY"]


def fetch_ordersheets(date: str, statuses=None):
    """date: YYYY-MM-DD. Returns list of order entries for that single day (KST),
    merged across all non-cancelled order statuses (a Coupang order only ever
    has one status at a time, so results from each status call don't overlap)."""
    statuses = statuses or ACTIVE_STATUSES
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{COUPANG_VENDOR_ID}/ordersheets"

    all_orders = []
    for status in statuses:
        params = {
            "createdAtFrom": date,
            "createdAtTo": date,
            "status": status,
            "maxPerPage": 50,
        }
        next_token = None
        while True:
            if next_token:
                params["nextToken"] = next_token
            data = _request("GET", path, params)
            orders = data.get("data", [])
            all_orders.extend(orders)
            next_token = data.get("nextToken")
            if not next_token:
                break
    return all_orders


def _is_target_item(item: dict) -> bool:
    """If COUPANG_TARGET_KEYWORD is unset, every item counts. Otherwise only line
    items whose name contains the keyword are counted -- useful when the same
    vendor account also sells other products under one seller ID."""
    if not COUPANG_TARGET_KEYWORD:
        return True
    name = item.get("sellerProductName", "") + item.get("vendorItemName", "")
    return COUPANG_TARGET_KEYWORD in name


def summarize_daily_sales(date: str):
    """Returns (order_count, item_quantity, sales_amount) for the given date based
    on ordersheets. If COUPANG_TARGET_KEYWORD is set, counts ONLY orders that are
    100% target-product line items (mixed orders are excluded entirely rather than
    prorated, since a bundled SKU can cover multiple products with no reliable
    per-item revenue split). sales_amount = item sales price + the order's full
    shippingPrice."""
    orders = fetch_ordersheets(date)
    order_count = 0
    item_quantity = 0
    sales_amount = 0.0
    for order in orders:
        items = order.get("orderItems", [])
        target_items = [i for i in items if _is_target_item(i)]
        if not target_items or len(target_items) != len(items):
            continue
        order_count += 1

        for item in target_items:
            qty = int(item.get("shippingCount", 1))
            item_quantity += qty
            sales_amount += float(item.get("salesPrice", 0)) * qty

        sales_amount += float(order.get("shippingPrice", 0))

    return order_count, item_quantity, sales_amount
