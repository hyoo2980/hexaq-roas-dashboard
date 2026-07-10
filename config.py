import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.environ.get("META_AD_ACCOUNT_ID", "")
# Comma-separated extra ad account IDs (same brand, multiple ad accounts/business portfolios)
META_AD_ACCOUNT_IDS = [a for a in (
    [META_AD_ACCOUNT_ID] + [s.strip() for s in os.environ.get("META_EXTRA_AD_ACCOUNT_IDS", "").split(",")]
) if a]

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
DISCORD_WEBHOOK_URL_ORDERS = os.environ.get("DISCORD_WEBHOOK_URL_ORDERS", "")

COUPANG_ACCESS_KEY = os.environ.get("COUPANG_ACCESS_KEY", "")
COUPANG_SECRET_KEY = os.environ.get("COUPANG_SECRET_KEY", "")
COUPANG_VENDOR_ID = os.environ.get("COUPANG_VENDOR_ID", "")
# Only count Coupang order line items containing this keyword. Leave blank to
# count all orders -- set this if the same seller account also sells other products.
COUPANG_TARGET_KEYWORD = os.environ.get("COUPANG_TARGET_KEYWORD", "")

CAFE24_CLIENT_ID = os.environ.get("CAFE24_CLIENT_ID", "")
CAFE24_CLIENT_SECRET = os.environ.get("CAFE24_CLIENT_SECRET", "")
CAFE24_MALL_ID = os.environ.get("CAFE24_MALL_ID", "")
CAFE24_REDIRECT_URI = os.environ.get("CAFE24_REDIRECT_URI", "")
CAFE24_REFRESH_TOKEN = os.environ.get("CAFE24_REFRESH_TOKEN", "")
# Only count Cafe24 orders whose line items contain this keyword in product_name.
# Leave blank to count all orders (no product filtering).
CAFE24_TARGET_KEYWORD = os.environ.get("CAFE24_TARGET_KEYWORD", "")

# Break-even ROAS used to estimate net profit (revenue/BEP_ROAS - spend).
# Leave unset (empty) to skip net-profit estimation entirely.
_bep = os.environ.get("BEP_ROAS", "")
BEP_ROAS = float(_bep) if _bep else None

ENV_PATH = ROOT_DIR / ".env"
DB_PATH = ROOT_DIR / "data" / "roas.db"


def get_env_value(key: str, default: str = "") -> str:
    """Re-reads a single key's current value straight from the .env file on disk,
    bypassing the cached module attribute. Needed for CAFE24_REFRESH_TOKEN: Cafe24
    rotates the refresh token on every use, and a long-running process (the
    realtime watcher) must not refresh using a stale in-memory copy that another
    process (the daily pipeline cron) may have already rotated on disk."""
    if not ENV_PATH.exists():
        return default
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line[len(key) + 1 :]
    return default


def update_env_value(key: str, value: str):
    """Persist a single key=value into the .env file, used for rotating Cafe24 refresh tokens.
    Also syncs to GitHub Actions Variable if GH_PAT + GITHUB_REPOSITORY are available,
    so the cloud order watcher always has the latest token."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # GitHub Variable 동기화 — 로컬 daily pipeline이 토큰 rotate 후 클라우드와 동기화
    gh_pat = os.environ.get("GH_PAT", "")
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if gh_pat and gh_repo:
        try:
            import requests as _req
            _req.patch(
                f"https://api.github.com/repos/{gh_repo}/actions/variables/{key}",
                headers={
                    "Authorization": f"Bearer {gh_pat}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={"name": key, "value": value},
                timeout=10,
            )
        except Exception:
            pass
