from __future__ import annotations

from playwright.sync_api import (
    BrowserContext,
    Frame,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from .selectors import POPUP_CLOSE_TEXTS, POPUP_DISMISS_TEXTS


def _click_visible_text(frame: Frame, texts: tuple[str, ...]) -> bool:
    for text in texts:
        locator = frame.get_by_text(text, exact=False)
        for index in range(locator.count()):
            candidate = locator.nth(index)
            if candidate.is_visible():
                candidate.click(timeout=1000)
                return True
    return False


def _close_notice_popup(page: Page) -> bool:
    """등록 페이지에서 비동기로 표시되는 공지 팝업을 닫는다."""

    popup = page.locator("#aipartner-popup-layout.notice-popup")
    if not popup.count():
        return False
    try:
        popup.wait_for(state="visible", timeout=4000)
    except PlaywrightTimeoutError:
        return False

    not_today = popup.locator(
        "label[for='popNotToday'], "
        "label[for^='popNotToday'], "
        "label:has-text('오늘 하루 보지 않기')"
    )
    for index in range(not_today.count()):
        candidate = not_today.nth(index)
        if candidate.is_visible():
            candidate.click()
            popup.wait_for(state="hidden", timeout=3000)
            return True

    close_buttons = popup.locator(".cancel, .close")
    for index in range(close_buttons.count()):
        candidate = close_buttons.nth(index)
        if candidate.is_visible():
            candidate.click()
            popup.wait_for(state="hidden", timeout=3000)
            return True
    return False


def close_popups(context: BrowserContext, main_page: Page) -> None:
    """메인 페이지, iframe, 별도 팝업의 일일 팝업을 닫는다."""

    for popup_page in list(context.pages):
        if popup_page.is_closed():
            continue
        try:
            _close_notice_popup(popup_page)
        except Exception:
            # 팝업이 닫히며 DOM이 동시에 제거되는 경우는 정상이다.
            pass
        for frame in popup_page.frames:
            try:
                if _click_visible_text(frame, POPUP_DISMISS_TEXTS):
                    break
                _click_visible_text(frame, POPUP_CLOSE_TEXTS)
            except Exception:
                # 클릭과 동시에 팝업 DOM 또는 창이 사라지는 경우는 정상이다.
                continue
        if popup_page != main_page and not popup_page.is_closed():
            try:
                popup_page.close()
            except Exception:
                continue
