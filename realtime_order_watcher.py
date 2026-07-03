import time
import traceback
from datetime import datetime
from pathlib import Path

from notify.realtime_orders import bootstrap_seen_orders, check_all_new_orders

POLL_INTERVAL_SECONDS = 300
LOG_PATH = Path(__file__).resolve().parent / "data" / "watcher.log"


def log(msg: str):
    """Writes to the OneDrive-synced log file, but never lets a transient file
    lock (OneDrive syncing the file at the same instant) or pythonw's
    consoleless stdout take down the whole watch loop -- a single failed write
    here must not kill hours of uptime."""
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line)
    except Exception:
        pass
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main():
    log("기존 주문 부트스트랩 중 (알림 발송 없이 기록만)...")
    try:
        bootstrap_seen_orders()
    except Exception:
        log("부트스트랩 중 오류:\n" + traceback.format_exc())
    log(f"실시간 주문 감시 시작 (폴링 간격 {POLL_INTERVAL_SECONDS}초)")
    while True:
        # Every step of one iteration -- including the log/flush calls -- is
        # inside this try so nothing (a transient OneDrive file lock, pythonw's
        # consoleless stdout, an API error) can ever take down the whole loop.
        try:
            counts = check_all_new_orders()
            log(f"checked -> {counts}")
        except Exception:
            log("폴링 중 오류 발생:\n" + traceback.format_exc())
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
