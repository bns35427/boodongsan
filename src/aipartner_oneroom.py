from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)

from .csv_loader import Listing
from .popup import close_popups
from .selectors import (
    ADDRESS_CONFIRM,
    DEAL_CODES,
    DEAL_LABELS,
    DIRECTION_BASIS,
    DIRECTION_CODES,
    DIRECTION_LABELS,
    IMAGE_EXTENSIONS,
    ONE_ROOM_DETAIL,
    ONE_ROOM_LARGE,
    OTHER_LISTING,
    SUBMIT_BUTTON,
    LocatorSpec,
)


class AIPartnerOneRoom:
    def __init__(
        self,
        page: Page,
        config: dict[str, Any],
        screenshots_dir: Path,
    ) -> None:
        self.page = page
        self.config = config
        self.site = config.get("site", {})
        self.options = config.get("options", {})
        self.screenshots_dir = screenshots_dir.resolve()
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def prepare_form(self) -> None:
        self.page.goto(self.site["ad_regist_url"], wait_until="domcontentloaded")
        close_popups(self.page.context, self.page)
        other = self._first_visible(OTHER_LISTING)
        if other is not None:
            other.click()

        self.page.locator("label[for='saleTypeD']").wait_for(
            state="visible",
            timeout=10000,
        )
        self._require_visible(ONE_ROOM_LARGE, "원룸 큰 버튼").click()
        self.page.locator("#detailTypeitemOR").wait_for(
            state="visible",
            timeout=10000,
        )
        self._require_visible(ONE_ROOM_DETAIL, "세부 원룸 버튼").click()
        self.page.locator("#registForm").wait_for(state="attached")
        self._verify_value("#setOfferingsGbn", "OR", "매물 종류")

    def fill(self, listing: Listing) -> None:
        deal_code = self._deal_code(listing.deal_type)
        self._fill_address(listing)
        self._choose_radio_label(
            f"label[for='setOfferGbn_{deal_code}']",
            DEAL_LABELS[deal_code],
        )
        self._verify_checked(f"#setOfferGbn_{deal_code}", "거래 유형")
        self._verify_value("#setOfferGbn", deal_code, "거래 유형 내부 코드")

        self._fill_prices(listing, deal_code)
        self._fill_input("#setSupSqr", listing.supply_area_m2, required=False)
        self._fill_input("#setExcSqr", listing.exclusive_area_m2)
        self._fill_input("#setFloor", listing.floor)
        self._fill_input("#setTotFloor", listing.total_floor)
        self._fill_input("#setRoomCnt", listing.room_count)
        self._fill_input("#setBathCnt", listing.bath_count)

        direction = DIRECTION_LABELS.get(listing.direction.strip())
        if not direction:
            raise ValueError(f"지원하지 않는 방향 값: {listing.direction}")
        self._select_custom("#selectDirectionCd", "#item-directionCd", direction)
        self._verify_value(
            "#setDirectionCd",
            DIRECTION_CODES[direction],
            "방향 내부 코드",
        )
        self._fill_direction_basis(listing.direction_basis)

        parking_label = "가능" if self._truthy(listing.parking) else "불가능"
        self._select_custom("#selectIsPark", "#item-isPark", parking_label)
        self._verify_value(
            "#setIsPark",
            "Y" if parking_label == "가능" else "N",
            "주차 내부 코드",
        )

        self._fill_maintenance_fee(listing.maintenance_fee)
        self._fill_options(listing)
        self._fill_input("#setMemo", listing.title)
        self._fill_input("#setDetailMemo", listing.memo)
        self._upload_photos(listing.photo_folder)

        # The site's date picker initializes asynchronously and can overwrite an
        # earlier value with today's date, so set and verify it last.
        self._fill_move_in_date(listing.move_in_date)
        self._verify_value("#setOfferingsGbn", "OR", "최종 매물 종류")
        self._verify_value("#setOfferGbn", deal_code, "최종 거래 유형")
        self._verify_move_in_date(listing.move_in_date)

    def ready_for_submit(self) -> None:
        button = self._require_visible(SUBMIT_BUTTON, "최종 광고하기 버튼")
        button.scroll_into_view_if_needed()
        if not button.is_enabled():
            raise RuntimeError("최종 광고하기 버튼이 비활성화되어 있습니다.")

    def submit(self) -> None:
        self.ready_for_submit()
        before_url = self.page.url
        self._require_visible(SUBMIT_BUTTON, "최종 광고하기 버튼").click()
        self._handle_submit_confirmation()
        try:
            self.page.wait_for_url(
                re.compile(r"/offerings/(ad_list|verification|modifyPopup)"),
                timeout=int(self.site.get("submit_timeout_ms", 30000)),
            )
        except PlaywrightTimeoutError:
            success_messages = (
                "등록되었습니다",
                "광고 등록이 완료",
                "매물 등록이 완료",
            )
            for message in success_messages:
                matches = self.page.get_by_text(message, exact=False)
                for index in range(matches.count()):
                    if matches.nth(index).is_visible():
                        return
            error_text = self._visible_error_text()
            raise RuntimeError(
                "등록 클릭 후 완료 상태를 확인하지 못했습니다. "
                f"이전 URL={before_url}, 현재 URL={self.page.url}"
                + (f" 화면 메시지: {error_text}" if error_text else "")
            )

    def screenshot(self, source_row: int, suffix: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.screenshots_dir / f"row_{source_row}_{suffix}_{timestamp}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def _first_visible(self, spec: LocatorSpec) -> Locator | None:
        candidates: list[Locator] = [self.page.locator(css) for css in spec.css]
        if spec.role:
            candidates.extend(
                self.page.get_by_role(spec.role, name=name, exact=True)
                for name in spec.role_names
            )
        candidates.extend(
            self.page.get_by_text(text, exact=True) for text in spec.text
        )
        for locator in candidates:
            for index in range(locator.count()):
                candidate = locator.nth(index)
                if candidate.is_visible():
                    return candidate
        return None

    def _require_visible(self, spec: LocatorSpec, description: str) -> Locator:
        locator = self._first_visible(spec)
        if locator is None:
            raise RuntimeError(f"{description}을(를) 찾지 못했습니다.")
        return locator

    def _fill_address(self, listing: Listing) -> None:
        for trigger, option_list, value in self._address_selections(listing):
            self._select_custom(trigger, option_list, value)

        if not listing.ri:
            area_li = self.page.locator("#areaLi")
            if area_li.count() and area_li.is_visible():
                raise RuntimeError(
                    "ri가 비어 있지만 사이트에서 리 선택을 요구합니다. "
                    "CSV의 ri 값을 확인하세요."
                )
        else:
            self.page.locator("#naddr4Text").wait_for(state="visible")

        main_no, sub_no = self._split_jibun(listing.jibun)
        self._fill_input("#setBun", main_no)
        self._fill_input("#setJi", sub_no, required=False)
        self._fill_input("#detailAddr", listing.detail_addr)
        self._require_visible(ADDRESS_CONFIRM, "주소확인 버튼").click()
        self._wait_for_address_confirmation(listing)

    @staticmethod
    def _address_selections(
        listing: Listing,
    ) -> list[tuple[str, str, str]]:
        selections = [
            ("#naddr1Text", "#naddr1List", listing.sido),
            ("#naddr2Text", "#naddr2List", listing.sigungu),
            ("#naddr3Text", "#naddr3List", listing.eupmyeon_dong),
        ]
        if listing.ri:
            selections.append(("#naddr4Text", "#naddr4List", listing.ri))
        return selections

    def _wait_for_address_confirmation(self, listing: Listing) -> None:
        complete = self.page.locator("button.btn-address-confirm-complete")
        map_ok = self.page.locator("#setMapOkYn")
        for attempt in range(3):
            ledger_loaded = self._load_building_ledger_from_popup(listing)
            if not ledger_loaded:
                if attempt < 2:
                    self._require_visible(
                        ADDRESS_CONFIRM,
                        "주소확인 재시도 버튼",
                    ).click()
                    continue
                break
            try:
                complete.wait_for(state="visible", timeout=10000)
                self._restore_detail_address(listing.detail_addr)
                return
            except PlaywrightTimeoutError:
                if map_ok.count() and map_ok.input_value() == "Y":
                    self._restore_detail_address(listing.detail_addr)
                    return
                if attempt < 2:
                    self._require_visible(
                        ADDRESS_CONFIRM,
                        "주소확인 재시도 버튼",
                    ).click()

        error_text = self._visible_error_text()
        raise RuntimeError(
            "건축물대장을 포함한 주소 확인이 3회 모두 완료되지 않았습니다."
            + (f" 화면 메시지: {error_text}" if error_text else "")
        )

    def _load_building_ledger_from_popup(self, listing: Listing) -> bool:
        confirmation_popup = self.page.locator(
            ".popup-layer-bold.popup-address-confirm"
        )
        try:
            confirmation_popup.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeoutError:
            return False

        ledger_candidates = (
            confirmation_popup.get_by_role(
                "button",
                name=re.compile(r"건축물대장\s*(불러오기|확인)"),
            ),
            confirmation_popup.get_by_role(
                "link",
                name=re.compile(r"건축물대장\s*(불러오기|확인)"),
            ),
            confirmation_popup.get_by_text(
                re.compile(r"^\s*건축물대장\s*(불러오기|확인)\s*$")
            ),
        )
        ledger_button = next(
            (
                candidate.nth(index)
                for candidate in ledger_candidates
                for index in range(candidate.count())
                if candidate.nth(index).is_visible()
            ),
            None,
        )
        if ledger_button is None:
            close_button = confirmation_popup.get_by_role(
                "button",
                name="닫기",
                exact=True,
            )
            if close_button.count():
                close_button.first.click()
            else:
                confirmation_popup.locator(".close").first.click()
            confirmation_popup.wait_for(state="hidden", timeout=5000)
            return False

        ledger_button.click()
        try:
            confirmation_popup.wait_for(state="hidden", timeout=15000)
        except PlaywrightTimeoutError as exc:
            error_text = self._visible_error_text()
            raise RuntimeError(
                "건축물대장 불러오기 완료를 확인하지 못했습니다."
                + (f" 화면 메시지: {error_text}" if error_text else "")
            ) from exc

        ledger_popup = self.page.locator(
            ".popup-layer-bold.popup-address-building-ledger"
        )
        if ledger_popup.count():
            ledger_popup.wait_for(state="visible", timeout=10000)
            building_trigger = ledger_popup.locator("a.select-info").nth(0)
            building_trigger.click()
            building_options = ledger_popup.locator(
                "a[data-building-register-pk]"
            ).filter(has_not_text="건물을 선택해 주세요")
            if not building_options.count():
                raise RuntimeError(
                    "건축물대장에서 선택 가능한 건물을 찾지 못했습니다."
                )
            selected_building = ledger_popup.locator(
                "a[data-building-register-pk][aria-selected='true']"
            )
            building_type = self._building_type(
                selected_building.first
                if selected_building.count() == 1
                else building_options.first,
                listing.building_dong,
            )
            if building_type == "집합" and listing.building_dong:
                target_dong = self._normalize_dong(listing.building_dong)
                building_option = next(
                    (
                        building_options.nth(index)
                        for index in range(building_options.count())
                        if target_dong
                        in self._normalize_dong(
                            building_options.nth(index).inner_text()
                        )
                    ),
                    None,
                )
                if building_option is None:
                    raise RuntimeError(
                        "건축물대장에서 CSV building_dong과 일치하는 동을 "
                        f"찾지 못했습니다: {listing.building_dong!r}"
                    )
            elif selected_building.count() == 1:
                building_option = selected_building.first
            else:
                building_option = building_options.first
                if building_options.count() > 1:
                    print(
                        "  [경고] 여러 건물이 조회되어 첫 건물을 선택합니다: "
                        f"{building_option.inner_text().strip()}"
                    )
            building_option.click()
            detail_trigger = ledger_popup.locator("a.select-info").nth(1)
            detail_scope = detail_trigger.locator("xpath=..")
            detail_options = detail_scope.locator("a").filter(
                has_not_text=re.compile(
                    r"선택해 주세요|건물 선택 후|상세주소를 선택"
                )
            )
            try:
                self.page.wait_for_function(
                    """popup => {
                        const trigger = popup.querySelectorAll(
                            'a.select-info'
                        )[1];
                        const scopes = trigger
                            ? trigger.parentElement.querySelectorAll('a')
                            : [];
                        const units = Array.from(scopes).filter(
                            el => !el.classList.contains('select-info')
                                && !el.textContent.includes('선택해 주세요')
                        );
                        return units.length > 0
                            || (
                                trigger
                                && !trigger.textContent.includes(
                                    '건물 선택 후 선택해 주세요'
                                )
                            );
                    }""",
                    arg=ledger_popup.element_handle(),
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                pass

            has_detail_options = bool(detail_options.count())
            if has_detail_options:
                detail_trigger.click()
                target_detail = (
                    self._normalize_unit(listing.detail_addr)
                    if building_type == "집합"
                    else self._normalize_floor(listing.floor)
                )
                matched_detail = next(
                    (
                        detail_options.nth(index)
                        for index in range(detail_options.count())
                        if (
                            self._normalize_unit(
                                detail_options.nth(index).inner_text()
                            )
                            if building_type == "집합"
                            else self._normalize_floor(
                                detail_options.nth(index).inner_text()
                            )
                        )
                        == target_detail
                    ),
                    None,
                )
                if matched_detail is None:
                    available_units = [
                        detail_options.nth(index).inner_text().strip()
                        for index in range(min(detail_options.count(), 20))
                    ]
                    raise RuntimeError(
                        "건축물대장에서 CSV "
                        f"{'상세주소' if building_type == '집합' else '층수'}와 "
                        "일치하는 항목을 찾지 못했습니다: "
                        f"{listing.detail_addr if building_type == '집합' else listing.floor!r}. "
                        f"확인된 항목(최대 20개)={available_units}"
                    )

                matched_text = matched_detail.inner_text().strip()
                matched_detail.click()
                expect(detail_trigger).to_have_text(
                    re.compile(rf"^\s*{re.escape(matched_text)}\s*$")
                )
            else:
                print(
                    "  [안내] 건축물대장에 호실 목록이 없어 건물 정보만 "
                    "적용하고 CSV 상세주소를 유지합니다."
                )
            apply_button = ledger_popup.get_by_text("적용하기", exact=True)
            apply_button.click()
            try:
                ledger_popup.wait_for(
                    state="hidden",
                    timeout=15000 if has_detail_options else 3000,
                )
            except PlaywrightTimeoutError:
                if has_detail_options:
                    raise
                print(
                    "  [안내] 적용 가능한 건축물대장 상세 정보가 없어 "
                    "팝업을 닫고 CSV 값으로 계속합니다."
                )
                close_button = ledger_popup.locator(".btn-close, .close")
                close_button.first.click()
                ledger_popup.wait_for(state="hidden", timeout=5000)
            loader = self.page.locator("#Ai_loader_container")
            if loader.count():
                try:
                    loader.wait_for(state="hidden", timeout=15000)
                except PlaywrightTimeoutError as exc:
                    raise RuntimeError(
                        "건축물대장 적용 후 로딩이 완료되지 않았습니다."
                    ) from exc

        # Building-ledger values are loaded asynchronously after the popup closes.
        self.page.wait_for_function(
            """() => {
                const mapOk = document.querySelector('#setMapOkYn');
                return !mapOk || mapOk.value === 'Y';
            }""",
            timeout=10000,
        )
        return True

    @staticmethod
    def _normalize_unit(value: str) -> str:
        normalized = re.sub(r"\s+", "", value.strip())
        return normalized[:-1] if normalized.endswith("호") else normalized

    @staticmethod
    def _normalize_dong(value: str) -> str:
        match = re.search(r"(\d+)\s*동", value)
        if match:
            return match.group(1)
        return re.sub(r"\D", "", value)

    @staticmethod
    def _normalize_floor(value: str) -> str:
        normalized = re.sub(r"\s+", "", value.strip())
        match = re.search(r"-?\d+", normalized)
        return match.group(0) if match else normalized.removesuffix("층")

    @staticmethod
    def _building_type(building: Locator, building_dong: str) -> str:
        explicit_type = (building.get_attribute("data-building-type") or "").strip()
        if explicit_type in {"일반", "집합"}:
            return explicit_type

        text = building.inner_text().strip()
        if text.startswith("[일반]"):
            return "일반"
        if text.startswith("[집합]"):
            return "집합"

        inferred = "집합" if building_dong.strip() else "일반"
        print(
            "  [경고] 건축물대장 유형 정보가 없어 CSV building_dong "
            f"유무로 {inferred} 건물로 판단합니다."
        )
        return inferred

    def _restore_detail_address(self, detail_addr: str) -> None:
        field = self.page.locator("#detailAddr")
        actual = field.input_value().strip()
        if actual == detail_addr.strip():
            return
        self._fill_input("#detailAddr", detail_addr)

    def _fill_prices(self, listing: Listing, deal_code: str) -> None:
        if deal_code == "M":
            self._fill_input("#setDepositPrc", listing.deposit)
            self._fill_input("#setMonthlyPrc", listing.monthly_rent)
        elif deal_code == "L":
            self._fill_input("#setLeasePrc", listing.deposit)
        elif deal_code == "S":
            self._fill_input("#setSellPrc", listing.deposit)
        elif deal_code == "T":
            self._fill_input("#setDepositPrc", listing.deposit)
            self._fill_input("#setMonthlyPrc", listing.monthly_rent)

    def _fill_move_in_date(self, raw_value: str) -> None:
        value = raw_value.strip()
        if value in {"", "즉시", "즉시입주", "immediate"}:
            self._choose_radio_label("label[for='moveGbn1']", "즉시입주")
            self._verify_checked("#moveGbn1", "입주가능일")
            self._verify_value("#moveGbn", "A", "입주가능일 내부 코드")
            return

        parsed = None
        for date_format in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                parsed = datetime.strptime(value, date_format)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(
                "move_in_date는 '즉시입주' 또는 YYYY-MM-DD 형식이어야 합니다."
            )
        self._choose_radio_label("label[for='moveGbn2']", "입주일지정")
        self._verify_checked("#moveGbn2", "입주일지정")
        self._verify_value("#moveGbn", "S", "입주가능일 내부 코드")
        date_value = parsed.strftime("%Y-%m-%d")
        self._select_calendar_date(parsed)
        self._verify_value(
            "#moveYmd",
            date_value,
            "입주 지정일",
        )
        expect(self.page.locator("#moveYmd_text")).to_have_text(date_value)

    def _select_calendar_date(self, target: datetime) -> None:
        calendar_link = self.page.locator(
            "a.calendarLink[data-id='moveYmd']"
        )
        calendar_link.click()
        calendar_box = calendar_link.locator("xpath=..")
        popup = calendar_box.locator(".popupLayer.calendar")
        popup.wait_for(state="visible")

        year_field = popup.locator(".dateInfo_year")
        month_field = popup.locator(".dateInfo_month")
        current_year = int(year_field.inner_text())
        current_month = int(month_field.inner_text())
        month_delta = (
            (target.year - current_year) * 12
            + target.month
            - current_month
        )
        direction = "next" if month_delta > 0 else "prev"

        for _ in range(abs(month_delta)):
            popup.locator(f".calendarHeader .{direction}").click()
            current_month += 1 if direction == "next" else -1
            if current_month == 13:
                current_year += 1
                current_month = 1
            elif current_month == 0:
                current_year -= 1
                current_month = 12
            expect(year_field).to_have_text(str(current_year))
            expect(month_field).to_have_text(f"{current_month:02d}")

        day_selector = (
            "li[onclick*='day_select("
            f"{target.year}, {target.month:02d}, {target.day}"
            ")']"
        )
        day = popup.locator(day_selector)
        day.wait_for(state="visible")
        day.click()
        popup.wait_for(state="hidden")

    def _verify_move_in_date(self, raw_value: str) -> None:
        value = raw_value.strip()
        if value in {"", "즉시", "즉시입주", "immediate"}:
            self._verify_checked("#moveGbn1", "최종 즉시입주")
            self._verify_value("#moveGbn", "A", "최종 입주가능일 내부 코드")
            return

        parsed = None
        for date_format in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                parsed = datetime.strptime(value, date_format)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(
                "move_in_date는 '즉시입주' 또는 YYYY-MM-DD 형식이어야 합니다."
            )
        self._verify_checked("#moveGbn2", "최종 입주일지정")
        self._verify_value("#moveGbn", "S", "최종 입주가능일 내부 코드")
        self._verify_value(
            "#moveYmd",
            parsed.strftime("%Y-%m-%d"),
            "최종 입주 지정일",
        )

    def _fill_direction_basis(self, raw_value: str) -> None:
        value = raw_value.strip()
        basis = DIRECTION_BASIS.get(value) or DIRECTION_BASIS.get(value.lower())
        if basis is None:
            raise ValueError(
                "direction_basis는 '거실' 또는 '안방'이어야 합니다: "
                f"{raw_value}"
            )
        label_selector, input_selector, expected_code = basis
        self._choose_radio_label(label_selector, value)
        self._verify_checked(input_selector, "방향기준")
        actual_code = self.page.locator(input_selector).get_attribute("value")
        if actual_code != expected_code:
            raise RuntimeError(
                "방향기준 내부 코드 검증 실패: "
                f"expected={expected_code!r}, actual={actual_code!r}"
            )

    def _fill_maintenance_fee(self, raw_value: str) -> None:
        fee = self._parse_decimal(raw_value, "maintenance_fee")
        multiplier = int(self.config.get("units", {}).get(
            "maintenance_fee_multiplier", 10000
        ))
        fee_won = int(fee * multiplier)

        if fee_won <= 0:
            self._choose_radio_label(
                "label[for='setSChargeCodeType3']", "확인불가"
            )
            self._select_custom(
                "#selectSUnableDetailCodeType",
                "#item-sUnableDetailCodeType",
                "관리비없음",
            )
            self._fill_input(
                "#sUnableDirectInputContent",
                str(self.config.get("maintenance_fee", {}).get(
                    "none_reason", "별도 관리비 없음"
                )),
            )
            return

        self._choose_radio_label(
            "label[for='setSChargeCodeType2']", "기타부과"
        )
        self._choose_radio_label(
            "label[for='setSChargeCriteriaCode1']", "직전월 관리비"
        )
        detail_type = str(
            self.config.get("maintenance_fee", {}).get(
                "detail_type", "정액관리비가 10만원 미만인 경우"
            )
        )
        self._select_custom(
            "#selectSFeeDetailCodeType",
            "#item-sFeeDetailCodeType",
            detail_type,
        )
        self._fill_input("#sEtcFeeAmount", str(fee_won))
        for label in self.config.get("maintenance_fee", {}).get(
            "included_items", []
        ):
            self._check_label(str(label), container="#trSFeeDetailCodeType")

    def _fill_options(self, listing: Listing) -> None:
        aircon = self._option_values(listing.option_aircon)
        if len(aircon) == 1 and self._truthy(aircon[0]):
            aircon = [
                str(self.options.get("default_aircon", "벽걸이에어컨"))
            ]
        for label in aircon:
            self._check_label(label, container="#tdAirconOption")
        for label in self._option_values(listing.option_life):
            self._check_label(label, container="#tdLifeOption")
        for label in self._option_values(listing.option_security):
            self._check_label(label, container="#tdSecurityOption")
        for label in self._option_values(listing.option_etc):
            self._check_label(label, container="#tdEtcOption")

    def _upload_photos(self, raw_folder: str) -> None:
        if not raw_folder.strip():
            return
        folder = Path(raw_folder).expanduser()
        if not folder.is_absolute():
            folder = Path.cwd() / folder
        folder = folder.resolve()
        if not folder.is_dir():
            message = f"사진 폴더를 찾을 수 없어 업로드를 건너뜁니다: {folder}"
            if self.config.get("photos", {}).get("fail_on_missing_folder", False):
                raise FileNotFoundError(message)
            print(f"  [경고] {message}")
            return

        photos = sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        max_photos = int(self.config.get("photos", {}).get("max_count", 20))
        photos = photos[:max_photos]
        if not photos:
            message = f"업로드 가능한 이미지가 없어 건너뜁니다: {folder}"
            if self.config.get("photos", {}).get("fail_on_empty_folder", False):
                raise ValueError(message)
            print(f"  [경고] {message}")
            return

        file_input = self.page.locator("#file, input[name='photoFiles[]']")
        existing_count = self.page.locator("#selectImage .imgItem").count()
        file_input.first.set_input_files([str(path) for path in photos])
        image_count = self.page.locator("#setImageCnt")
        try:
            self.page.locator("#selectImage .imgItem").nth(
                existing_count + len(photos) - 1
            ).wait_for(state="attached", timeout=30000)
        except PlaywrightTimeoutError:
            expected_count = existing_count + len(photos)
            if (
                not image_count.count()
                or int(image_count.input_value() or "0") < expected_count
            ):
                raise RuntimeError("사진 업로드 완료를 확인하지 못했습니다.")

        uploaded_count = self.page.locator("#selectImage .imgItem").count()
        expected_count = existing_count + len(photos)
        if uploaded_count < expected_count:
            raise RuntimeError(
                f"사진 업로드 개수 검증 실패: expected={expected_count}, "
                f"actual={uploaded_count}"
            )
        print(f"  사진 업로드 확인: {len(photos)}장")

    def _select_custom(
        self,
        trigger_selector: str,
        list_selector: str,
        option_text: str,
    ) -> None:
        trigger = self.page.locator(trigger_selector)
        trigger.wait_for(state="visible")
        trigger.click()
        options = self.page.locator(f"{list_selector} a").filter(
            has_text=re.compile(rf"^\s*{re.escape(option_text)}\s*$")
        )
        options.first.wait_for(state="visible")
        options.first.scroll_into_view_if_needed()
        options.first.click()
        self._verify_text(trigger_selector, option_text)

    def _choose_radio_label(self, selector: str, fallback_text: str) -> None:
        label = self.page.locator(selector)
        if not label.count() or not label.first.is_visible():
            label = self.page.get_by_text(fallback_text, exact=True)
        label.first.wait_for(state="visible")
        label.first.click()

    def _check_label(self, label_text: str, container: str) -> None:
        scope = self.page.locator(container)
        label = scope.locator("label").filter(
            has_text=re.compile(rf"^\s*{re.escape(label_text)}\s*$")
        )
        if not label.count():
            raise ValueError(f"사이트에서 옵션을 찾지 못했습니다: {label_text}")
        for_attr = label.first.get_attribute("for")
        label.first.click()
        if for_attr:
            self._verify_checked(f"#{for_attr}", f"옵션 {label_text}")

    def _fill_input(
        self,
        selector: str,
        value: str,
        required: bool = True,
    ) -> None:
        if required and value == "":
            raise ValueError(f"필수 값이 비어 있습니다: {selector}")
        field = self.page.locator(selector)
        field.wait_for(state="visible")
        if field.is_disabled():
            field.evaluate("(el) => el.removeAttribute('disabled')")
        field.fill(value)
        field.dispatch_event("input")
        field.dispatch_event("change")
        if field.input_value().strip() != value.strip():
            raise RuntimeError(
                f"입력값 검증 실패: {selector}={field.input_value()!r}, "
                f"expected={value!r}"
            )

    def _verify_value(
        self, selector: str, expected: str, description: str
    ) -> None:
        field = self.page.locator(selector)
        if not field.count():
            raise RuntimeError(f"{description} 내부 필드를 찾지 못했습니다: {selector}")
        actual = field.first.input_value()
        if actual != expected:
            raise RuntimeError(
                f"{description} 검증 실패: expected={expected!r}, actual={actual!r}"
            )

    def _verify_text(
        self, selector: str, expected: str
    ) -> None:
        actual = " ".join(self.page.locator(selector).inner_text().split())
        if actual != expected:
            raise RuntimeError(
                f"선택값 검증 실패: {selector} expected={expected!r}, actual={actual!r}"
            )

    def _verify_checked(self, selector: str, description: str) -> None:
        locator = self.page.locator(selector)
        if not locator.count() or not locator.first.is_checked():
            raise RuntimeError(f"{description} 선택 검증에 실패했습니다.")

    def _handle_submit_confirmation(self) -> None:
        popup_selectors = (
            ".popupContentWrap[aria-hidden='false']",
            ".modal",
            "[role='dialog']",
        )
        for popup_selector in popup_selectors:
            popup = self.page.locator(popup_selector)
            for index in range(popup.count()):
                candidate_popup = popup.nth(index)
                if not candidate_popup.is_visible():
                    continue
                for text in ("확인", "광고하기", "등록"):
                    buttons = candidate_popup.get_by_role(
                        "button", name=text, exact=True
                    )
                    for button_index in range(buttons.count()):
                        button = buttons.nth(button_index)
                        if button.is_visible():
                            button.click()
                            return

    def _visible_error_text(self) -> str:
        selectors = (
            ".alert",
            ".error",
            ".validation-message",
            ".popupContentWrap[aria-hidden='false']",
        )
        messages: list[str] = []
        for selector in selectors:
            locator = self.page.locator(selector)
            for index in range(min(locator.count(), 5)):
                item = locator.nth(index)
                if item.is_visible():
                    text = " ".join(item.inner_text().split())
                    if text:
                        messages.append(text[:300])
        return " | ".join(messages)

    @staticmethod
    def _split_jibun(value: str) -> tuple[str, str]:
        parts = value.strip().split("-", 1)
        main_no = parts[0].strip()
        sub_no = parts[1].strip() if len(parts) == 2 else ""
        if not main_no.isdigit() or (sub_no and not sub_no.isdigit()):
            raise ValueError(f"지번 형식이 올바르지 않습니다: {value}")
        return main_no, sub_no

    @staticmethod
    def _deal_code(value: str) -> str:
        code = DEAL_CODES.get(value.strip().lower()) or DEAL_CODES.get(
            value.strip()
        )
        if not code:
            raise ValueError(f"지원하지 않는 거래 유형: {value}")
        return code

    @staticmethod
    def _parse_decimal(value: str, field_name: str) -> float:
        try:
            return float(value.replace(",", "").strip() or "0")
        except ValueError as exc:
            raise ValueError(f"{field_name} 숫자 형식이 아닙니다: {value}") from exc

    @staticmethod
    def _truthy(value: str) -> bool:
        return value.strip().lower() in {
            "1",
            "true",
            "t",
            "yes",
            "y",
            "가능",
            "있음",
        }

    @staticmethod
    def _option_values(value: str) -> list[str]:
        return [
            item.strip()
            for item in re.split(r"[|,]", value)
            if item.strip()
        ]
