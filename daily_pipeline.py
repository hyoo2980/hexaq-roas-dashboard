import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

from collect_cafe24_range import main as collect_cafe24
from collect_coupang_range import main as collect_coupang
from collect_meta_range import main as collect_meta
from notify.discord import send_daily_report

LOG_PATH = Path(__file__).resolve().parent / "data" / "pipeline.log"


def log(msg: str):
    """Mirrors to a log file -- when this runs under Task Scheduler there's no
    console attached, so print() alone leaves no trace to diagnose failures."""
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


def run(report_date: str):
    log(f"=== 일일 파이프라인 시작: {report_date} ===")

    log("[1/4] 메타 데이터 수집")
    collect_meta(report_date, report_date)

    log("[2/4] 카페24 데이터 수집")
    collect_cafe24(report_date, report_date)

    log("[3/4] 쿠팡 데이터 수집")
    collect_coupang(report_date, report_date)

    log("[4/4] 디스코드 리포트 발송")
    send_daily_report(report_date)

    log(f"=== 일일 파이프라인 완료: {report_date} ===")


if __name__ == "__main__":
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    try:
        run(yesterday)
    except Exception:
        log("파이프라인 실패:\n" + traceback.format_exc())
        sys.exit(1)
