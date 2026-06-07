from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

from playwright.sync_api import (
    Dialog,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from .popup import close_popups
from .selectors import LOGIN_BUTTON, LOGIN_ID, LOGIN_PASSWORD, LocatorSpec


def _first_visible(page: Page, spec: LocatorSpec) -> Locator | None:
    candidates: list[Locator] = [page.locator(css) for css in spec.css]
    if spec.role:
        candidates.extend(
            page.get_by_role(spec.role, name=name, exact=True)
            for name in spec.role_names
        )
    candidates.extend(page.get_by_text(text, exact=True) for text in spec.text)
    for locator in candidates:
        for index in range(locator.count()):
            candidate = locator.nth(index)
            if candidate.is_visible():
                return candidate
    return None


def _require_visible(page: Page, spec: LocatorSpec, description: str) -> Locator:
    locator = _first_visible(page, spec)
    if locator is None:
        raise RuntimeError(f"{description} 요소를 찾지 못했습니다.")
    return locator


def login(
    page: Page,
    ad_regist_url: str,
    member_id: str,
    password: str,
    logged_in_markers: Iterable[str] = ("#registForm", "button.btnOtherItem"),
) -> None:
    page.goto(ad_regist_url, wait_until="domcontentloaded")
    close_popups(page.context, page)

    id_field = _first_visible(page, LOGIN_ID)
    if id_field is not None:
        print("  [로그인] 세션이 없어 .env 계정으로 자동 로그인합니다.")
        dialog_messages: list[str] = []

        def capture_dialog(dialog: Dialog) -> None:
            dialog_messages.append(dialog.message)
            dialog.dismiss()

        page.on("dialog", capture_dialog)
        id_field.fill(member_id)
        _require_visible(page, LOGIN_PASSWORD, "비밀번호 입력").fill(password)
        _require_visible(page, LOGIN_BUTTON, "로그인 버튼").click()
        target = urlparse(ad_regist_url)
        target_url = re.compile(
            rf"^https?://{re.escape(target.netloc)}"
            rf"{re.escape(target.path.rstrip('/'))}/?(?:\?.*)?$"
        )
        try:
            page.wait_for_url(
                target_url,
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except PlaywrightTimeoutError as exc:
            detail = (
                " | ".join(dialog_messages)
                if dialog_messages
                else "로그인 페이지에서 30초 동안 이동하지 않았습니다."
            )
            raise RuntimeError(
                f"로그인에 실패했습니다: {detail} 현재 URL={page.url}"
            ) from exc
        finally:
            page.remove_listener("dialog", capture_dialog)

        close_popups(page.context, page)
        if page.url.rstrip("/") != ad_regist_url.rstrip("/"):
            page.goto(ad_regist_url, wait_until="domcontentloaded")
    else:
        print("  [로그인] 저장된 로그인 세션을 재사용합니다.")

    marker_selector = ", ".join(logged_in_markers)
    try:
        page.locator(marker_selector).first.wait_for(
            state="attached",
            timeout=15000,
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "로그인 후 매물 등록 페이지를 확인하지 못했습니다. "
            f"현재 URL={page.url}. 추가 인증 또는 이용 권한을 확인하세요."
        ) from exc
