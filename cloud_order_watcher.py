"""GitHub Actions에서 5분마다 실행되는 주문 알림 스크립트 (헥사큐 아쿠아메딘).

Cafe24 채널만 체크 (쿠팡은 실시간 알림 불필요, 네이버 없음).
루프 없이 1회 실행 후 종료.
상태(알림 보낸 주문 ID + 오늘 누적금액)는 data/notified_cloud.json에 저장하고,
GitHub Actions cache로 run 간에 유지한다.

Cafe24 리프레시 토큰 갱신은 .env 대신 GitHub Repository Variables API(GH_PAT)로 저장.
"""

import json
import os
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests as http

# ──────────────────────────────────────────────────────────────────
# config 패치 — GitHub Actions 환경에서 .env 없이 동작
# ──────────────────────────────────────────────────────────────────
import config


def _update_github_variable(name: str, value: str):
    # GITHUB_TOKEN은 Variables API 수정 권한 없음 → PAT(GH_PAT) 사용
    gh_token = os.environ.get("GH_PAT", "") or os.environ.get("GITHUB_TOKEN", "")
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not gh_token or not gh_repo:
        print(f"[WARN] GitHub variable 업데이트 불가 ({name})")
        return
    resp = http.patch(
        f"https://api.github.com/repos/{gh_repo}/actions/variables/{name}",
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"name": name, "value": value},
        timeout=10,
    )
    if resp.ok:
        print(f"[INFO] GitHub variable '{name}' 갱신 완료")
    else:
        print(f"[WARN] GitHub variable '{name}' 갱신 실패: {resp.status_code} {resp.text[:200]}")


def _patched_update_env(key: str, value: str):
    _update_github_variable(key, value)
    setattr(config, key, value)
    os.environ[key] = value


def _patched_get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


config.update_env_value = _patched_update_env
config.get_env_value = _patched_get_env

# ──────────────────────────────────────────────────────────────────
# 상태 관리
# ──────────────────────────────────────────────────────────────────
STATE_PATH = Path("data/notified_cloud.json")


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────
# Discord 알림
# ──────────────────────────────────────────────────────────────────
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL_ORDERS", "")


def send_alert(order_id: str, amount: float, cumulative: float, detail: str = ""):
    if not WEBHOOK_URL:
        print("[WARN] DISCORD_WEBHOOK_URL_ORDERS 미설정")
        return
    embed = {
        "title": "🛍️ 새 주문 — 자사몰(카페24)",
        "color": 0x1E88E5,
        "fields": [
            {"name": "주문번호", "value": str(order_id), "inline": True},
            {"name": "금액", "value": f"{amount:,.0f}원", "inline": True},
            {"name": "오늘 누적 결제금액", "value": f"{cumulative:,.0f}원", "inline": True},
        ],
    }
    if detail:
        embed["fields"].append({"name": "상세", "value": detail, "inline": False})
    # Discord 429 재시도
    delay = 2.0
    for _ in range(4):
        resp = http.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=30)
        if resp.status_code == 429:
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return
    resp.raise_for_status()


# ──────────────────────────────────────────────────────────────────
# 주문 체크
# ──────────────────────────────────────────────────────────────────
def check_cafe24(today: str, seen: dict, cumulative: float, is_bootstrap: bool) -> tuple[int, float]:
    from collectors.cafe24 import _is_target_item, fetch_orders

    orders = fetch_orders(today)
    new_count = 0
    for o in orders:
        items = o.get("items", [])
        target_items = [i for i in items if _is_target_item(i)]
        if not target_items or len(target_items) != len(items):
            continue

        oid = o["order_id"]
        key = f"cafe24:{oid}"
        if key in seen:
            continue

        amount = float(o.get("actual_order_amount", {}).get("payment_amount", 0))
        if is_bootstrap:
            seen[key] = amount
            cumulative += amount
        else:
            cumulative += amount
            names = ", ".join(i.get("product_name", "") for i in target_items)
            send_alert(oid, amount, cumulative, detail=names)
            seen[key] = amount
            new_count += 1

    return new_count, cumulative


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────
_KST = timezone(timedelta(hours=9))


def main():
    today = datetime.now(_KST).date().isoformat()

    state = load_state()
    if state.get("date") != today:
        state = {"date": today, "seen": {}, "cumulative": 0.0}
        is_bootstrap = True
        print(f"[INFO] 새 날짜({today}) — 상태 초기화 및 부트스트랩 실행")
    elif not state.get("seen"):
        is_bootstrap = True
        print(f"[INFO] seen이 비어있음 — 부트스트랩 재실행")
    else:
        is_bootstrap = False

    seen: dict = state.get("seen", {})
    cumulative: float = float(state.get("cumulative", 0.0))

    print(f"[INFO] 날짜={today}, 부트스트랩={is_bootstrap}, seen={len(seen)}건, 누적={cumulative:,.0f}원")

    try:
        new_c, cumulative = check_cafe24(today, seen, cumulative, is_bootstrap)
        print(f"[INFO] Cafe24: 신규 알림 {new_c}건")
    except Exception:
        print(f"[ERROR] Cafe24 체크 실패:\n{traceback.format_exc()}")

    state["seen"] = seen
    state["cumulative"] = cumulative
    save_state(state)
    print(f"[INFO] 완료 — seen 총 {len(seen)}건, 누적={cumulative:,.0f}원")


if __name__ == "__main__":
    main()
