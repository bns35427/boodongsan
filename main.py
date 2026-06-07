from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from src.aipartner_oneroom import AIPartnerOneRoom
from src.browser import BrowserSession
from src.csv_loader import Listing, load_listings
from src.logger import ResultLogger, ResultRecord
from src.login import login


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CSV 기반 이실장 원룸 매물 광고 등록 자동화"
    )
    parser.add_argument("--csv", default="mamuls.csv", help="입력 CSV 경로")
    parser.add_argument("--config", default="config.json", help="설정 JSON 경로")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="최종 광고하기 버튼 직전에서 멈춤(기본값)",
    )
    mode.add_argument(
        "--submit",
        action="store_true",
        help="최종 광고하기 버튼을 클릭해 실제 등록",
    )
    parser.add_argument(
        "--row",
        type=int,
        help="CSV 데이터 순번 하나만 처리(헤더 제외, 1부터 시작)",
    )
    parser.add_argument(
        "--close-on-finish",
        action="store_true",
        help="dry-run 완료 후 브라우저를 유지하지 않고 즉시 종료",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"config.json을 찾을 수 없습니다: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def credentials() -> tuple[str, str]:
    load_dotenv()
    member_id = os.getenv("AIPARTNER_ID", "").strip()
    password = os.getenv("AIPARTNER_PW", "")
    if not member_id or not password:
        raise ValueError(
            ".env에 AIPARTNER_ID와 AIPARTNER_PW를 설정해야 합니다."
        )
    return member_id, password


def select_rows(listings: list[Listing], row_number: int | None) -> list[Listing]:
    if row_number is None:
        return listings
    if not 1 <= row_number <= len(listings):
        raise ValueError(f"--row는 1~{len(listings)} 범위여야 합니다.")
    return [listings[row_number - 1]]


def address_text(listing: Listing) -> str:
    return " ".join(
        value
        for value in (
            listing.sido,
            listing.sigungu,
            listing.eupmyeon_dong,
            listing.ri,
            listing.jibun,
            listing.detail_addr,
        )
        if value
    )


def main() -> int:
    args = parse_args()
    submit = bool(args.submit)
    mode_name = "submit" if submit else "dry-run"
    config = load_config(Path(args.config))
    listings, warnings = load_listings(Path(args.csv))
    listings = select_rows(listings, args.row)
    member_id, password = credentials()

    for warning in warnings:
        print(f"[경고] {warning}")
    print(f"[시작] {len(listings)}개 행, 모드={mode_name}")
    if not submit:
        print("[안전] --submit이 없으므로 실제 광고 등록 버튼은 누르지 않습니다.")

    paths = config.get("paths", {})
    result_logger = ResultLogger(Path(paths.get("result_csv", "logs/result.csv")))
    screenshots_dir = Path(paths.get("screenshots_dir", "screenshots"))

    with sync_playwright() as playwright:
        session = BrowserSession(playwright, config)
        first_page = session.start()
        try:
            for index, listing in enumerate(listings, start=1):
                print(
                    f"[{index}/{len(listings)}] 창 열기 및 처리: "
                    f"{listing.display_name}"
                )
                screenshot_path = ""
                page = first_page if index == 1 else session.new_window()
                try:
                    login(
                        page=page,
                        ad_regist_url=config["site"]["ad_regist_url"],
                        member_id=member_id,
                        password=password,
                    )
                    session.save_storage_state()
                    automation = AIPartnerOneRoom(
                        page,
                        config,
                        screenshots_dir,
                    )
                    automation.prepare_form()
                    automation.fill(listing)
                    automation.ready_for_submit()
                    if submit:
                        automation.submit()
                        status = "success"
                    else:
                        screenshot_path = str(
                            automation.screenshot(listing.source_row, "dry_run")
                        )
                        status = "dry_run_ready"
                    result_logger.write(
                        ResultRecord(
                            source_row=listing.source_row,
                            status=status,
                            mode=mode_name,
                            title=listing.title,
                            address=address_text(listing),
                            current_url=page.url,
                            screenshot_path=screenshot_path,
                        )
                    )
                    print(f"  완료: {status}")
                except Exception as exc:
                    try:
                        screenshots_dir.mkdir(parents=True, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        failed_path = (
                            screenshots_dir
                            / f"row_{listing.source_row}_failed_{timestamp}.png"
                        ).resolve()
                        page.screenshot(
                            path=str(failed_path),
                            full_page=True,
                        )
                        screenshot_path = str(failed_path)
                    except Exception:
                        screenshot_path = ""
                    result_logger.write(
                        ResultRecord(
                            source_row=listing.source_row,
                            status="failed",
                            mode=mode_name,
                            title=listing.title,
                            address=address_text(listing),
                            current_url=page.url,
                            error_message=f"{type(exc).__name__}: {exc}",
                            screenshot_path=screenshot_path,
                        )
                    )
                    print(f"  실패: {type(exc).__name__}: {exc}", file=sys.stderr)
                    continue

            if not submit and not args.close_on_finish:
                print(
                    f"[대기] {len(listings)}개 행별 브라우저 창을 유지합니다. "
                    "검토와 수정을 마친 창은 직접 닫으세요."
                )
                session.wait_until_closed()
        finally:
            session.close()

    print(f"[완료] 결과 로그: {result_logger.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
