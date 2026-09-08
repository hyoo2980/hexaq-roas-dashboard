"""GitHub Actions에서 2분마다 실행되는 주문 알림 스크립트 (헥사큐 아쿠아메딘).

Cafe24 채널만 체크 (쿠팡은 실시간 알림 불필요, 네이버 없음).
루프 없이 1회 실행 후 종료.
상태(알림 보낸 주문 ID + 오늘 누적금액)는 GitHub Variable(ORDER_STATE)에 저장.
GitHub Actions cache 대신 Variable을 사용해 캐시 미스로 인한 오중복 bootstrap을 방지.

Cafe24 리프레시 토큰 갱신은 .env 대신 GitHub Repository Variables API(GH_PAT)로 저장.
"""

import json
import os
import time
import traceback
from datetime import datetime, timezone, timedelta

import requests as http

# ──────────────────────────────────────────────────────────────────
# config 패치 — GitHub Actions 환경에서 .env 없이 동작
# ──────────────────────────────────────────────────────────────────
import config


def _update_github_variable(name: str, value: str):
    gh_token = os.environ.get("GH_PAT", "") or os.environ.get("GITHUB_TOKEN", "")
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not gh_token or not gh_repo:
        print(f"[WARN] GitHub variable 업데이트 불가 ({name}): GH_PAT/GITHUB_REPOSITORY 미설정")
        return
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base_url = f"https://api.github.com/repos/{gh_repo}/actions/variables"
    try:
        resp = http.patch(f"{base_url}/{name}", headers=headers, json={"name": name, "value": value}, timeout=10)
        if resp.status_code == 404:
            resp = http.post(base_url, headers=headers, json={"name": name, "value": value}, timeout=10)
        if resp.ok:
            print(f"[INFO] GitHub variable '{name}' 갱신 완료")
        else:
            print(f"[WARN] GitHub variable '{name}' 갱신 실패: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"[WARN] GitHub variable '{name}' 갱신 중 네트워크 오류 (무시): {e}")


def _patched_update_env(key: str, value: str):
    _update_github_variable(key, value)
    setattr(config, key, value)
    os.environ[key] = value


def _patched_get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


config.update_env_value = _patched_update_env
config.get_env_value = _patched_get_env

# ──────────────────────────────────────────────────────────────────
# Cafe24 access token 캐시 주입 (2시간마다만 rotate)
# ──────────────────────────────────────────────────────────────────
def _inject_cached_access_token():
    cached_token = os.environ.get("CAFE24_ACCESS_TOKEN", "")
    expires_at_str = os.environ.get("CAFE24_ACCESS_TOKEN_EXPIRES_AT", "")
    if not cached_token or not expires_at_str:
        return
    try:
        expires_at = datetime.fromisoformat(expires_at_str.rstrip("0").rstrip("."))
        expires_at = expires_at.replace(tzinfo=timezone(timedelta(hours=9)))
        if expires_at > datetime.now(timezone(timedelta(hours=9))) + timedelta(minutes=5):
            import collectors.cafe24 as _c24
            _c24._token_cache["access_token"] = cached_token
            print(f"[INFO] 캐시된 access token 재사용 (만료: {expires_at_str})")
    except Exception as e:
        print(f"[INFO] access token 캐시 로드 실패 ({e}) — 재발급 진행")

_inject_cached_access_token()

# ──────────────────────────────────────────────────────────────────
# 상태 관리 — GitHub Variable(ORDER_STATE) 기반
# GitHub Actions cache는 캐시 미스 시 오래된 상태를 복원해 bootstrap이 중복 실행되는
# 문제가 있으므로 완전히 영속적인 Variable로 대체.
# ──────────────────────────────────────────────────────────────────
_GH_VAR_NAME = "ORDER_STATE"


def _get_github_variable(name: str) -> str:
    gh_token = os.environ.get("GH_PAT", "") or os.environ.get("GITHUB_TOKEN", "")
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not gh_token or not gh_repo:
        return ""
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = http.get(
        f"https://api.github.com/repos/{gh_repo}/actions/variables/{name}",
        headers=headers, timeout=10,
    )
    if resp.ok:
        return resp.json().get("value", "")
    return ""


def load_state() -> dict:
    raw = _get_github_variable(_GH_VAR_NAME)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    _update_github_variable(_GH_VAR_NAME, json.dumps(state, ensure_ascii=False))


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

    yesterday = (datetime.now(_KST).date() - timedelta(days=1)).isoformat()

    state = load_state()
    prev_date = state.get("date")

    if prev_date == yesterday and "seen" in state:
        # 정상적인 날짜 롤오버. 어제까지 상태가 멀쩡했으므로 새 날에는 밀린 주문이
        # 존재할 수 없고, 조회되는 주문은 전부 진짜 신규다. 여기서 부트스트랩하면
        # 자정 직후(00:00~00:02)에 들어온 주문이 매일 무음 처리되어 사라진다.
        #
        # 넘어가기 전에 어제를 마지막으로 한 번 더 훑는다. 어제의 마지막 폴링(23:58)과
        # 자정 사이에 들어온 주문은 아직 아무도 본 적이 없는데, 오늘 날짜로 조회하면
        # order_date가 어제라 영영 잡히지 않고 사라진다.
        try:
            late, _ = check_cafe24(
                yesterday, state["seen"], float(state.get("cumulative", 0.0)), False
            )
            if late:
                print(f"[INFO] 어제({yesterday}) 마감 직전 주문 {late}건 알림 발송")
        except Exception:
            print(f"[ERROR] 어제({yesterday}) 마감 스윕 실패:")
            print(traceback.format_exc())

        state = {"date": today, "seen": {}, "cumulative": 0.0}
        is_bootstrap = False
        print(f"[INFO] 날짜 롤오버({yesterday}→{today}) — 상태 초기화, 알림은 즉시 발송")
    elif prev_date != today or "seen" not in state:
        # 상태 유실 또는 장기 중단(하루 이상 공백). 그날 이미 쌓인 주문이 한꺼번에
        # 쏟아지는 것을 막기 위해 무음 부트스트랩한다.
        state = {"date": today, "seen": {}, "cumulative": 0.0}
        is_bootstrap = True
        print(f"[INFO] 상태 유실/장기 중단 감지(이전 날짜={prev_date}) — 부트스트랩 실행")
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
