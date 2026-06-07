from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
)


class BrowserSession:
    def __init__(self, playwright: Playwright, config: dict[str, Any]) -> None:
        self.playwright = playwright
        self.config = config
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.storage_state_path: Path | None = None

    def start(self) -> Page:
        browser_config = self.config.get("browser", {})
        headless = bool(browser_config.get("headless", False))
        slow_mo = int(browser_config.get("slow_mo_ms", 0))
        viewport = browser_config.get("viewport", {"width": 1440, "height": 1000})
        profile_dir = str(browser_config.get("user_data_dir", "")).strip()

        if profile_dir:
            profile_path = Path(profile_dir).expanduser().resolve()
            profile_path.mkdir(parents=True, exist_ok=True)
            self.storage_state_path = profile_path / "storage_state.json"
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=headless,
                slow_mo=slow_mo,
                viewport=viewport,
            )
            self.page = (
                self.context.pages[0] if self.context.pages else self.context.new_page()
            )
        else:
            self.browser = self.playwright.chromium.launch(
                headless=headless,
                slow_mo=slow_mo,
            )
            self.context = self.browser.new_context(viewport=viewport)
            self.page = self.context.new_page()

        timeout_ms = int(self.config.get("site", {}).get("timeout_ms", 15000))
        navigation_timeout_ms = int(
            self.config.get("site", {}).get("navigation_timeout_ms", 30000)
        )
        self.context.set_default_timeout(timeout_ms)
        self.context.set_default_navigation_timeout(navigation_timeout_ms)
        self._restore_storage_state()
        return self.page

    def new_window(self) -> Page:
        """같은 로그인 컨텍스트를 공유하는 새 Chromium 창을 연다."""

        if self.context is None:
            raise RuntimeError("브라우저 세션이 시작되지 않았습니다.")
        if self.page is None or self.page.is_closed():
            self.page = (
                self.context.pages[0]
                if self.context.pages
                else self.context.new_page()
            )

        try:
            cdp = self.context.new_cdp_session(self.page)
            with self.context.expect_page(timeout=10000) as page_info:
                cdp.send(
                    "Target.createTarget",
                    {"url": "about:blank", "newWindow": True},
                )
            page = page_info.value
            cdp.detach()
            return page
        except PlaywrightError:
            # Chromium 정책상 새 창 생성이 막히면 같은 컨텍스트의 새 탭을 쓴다.
            return self.context.new_page()

    def close(self) -> None:
        self.save_storage_state()
        if self.context is not None:
            try:
                self.context.close()
            except PlaywrightError:
                pass
        if self.browser is not None:
            try:
                self.browser.close()
            except PlaywrightError:
                pass

    def wait_until_closed(self) -> None:
        """사용자가 마지막 브라우저 창을 닫을 때까지 세션을 유지한다."""

        if self.context is None:
            return
        print(
            "[대기] 브라우저를 열어 두었습니다. "
            "사진 추가와 내용 수정을 마친 뒤 브라우저 창을 직접 닫으세요."
        )
        try:
            while self.context.pages:
                active_page = self.context.pages[-1]
                active_page.wait_for_timeout(1000)
        except KeyboardInterrupt:
            print("\n[종료] 사용자 요청으로 브라우저 세션을 닫습니다.")
        except PlaywrightError:
            # 사용자가 마지막 창을 닫는 순간 대기 호출이 중단될 수 있다.
            pass

    @property
    def has_open_pages(self) -> bool:
        return self.context is not None and bool(self.context.pages)

    def save_storage_state(self) -> None:
        if self.context is None or self.storage_state_path is None:
            return
        try:
            self.context.storage_state(path=str(self.storage_state_path))
        except PlaywrightError:
            pass

    def _restore_storage_state(self) -> None:
        if (
            self.context is None
            or self.storage_state_path is None
            or not self.storage_state_path.is_file()
        ):
            return
        try:
            state = json.loads(
                self.storage_state_path.read_text(encoding="utf-8")
            )
            cookies = state.get("cookies", [])
            if cookies:
                self.context.add_cookies(cookies)

            local_storage = {
                origin["origin"]: origin.get("localStorage", [])
                for origin in state.get("origins", [])
                if origin.get("origin")
            }
            if local_storage:
                serialized = json.dumps(
                    local_storage,
                    ensure_ascii=True,
                )
                self.context.add_init_script(
                    script=f"""
                        (() => {{
                            const states = {serialized};
                            const entries = states[window.location.origin] || [];
                            for (const item of entries) {{
                                window.localStorage.setItem(
                                    item.name,
                                    item.value
                                );
                            }}
                        }})();
                    """
                )
        except (OSError, ValueError, PlaywrightError):
            pass
