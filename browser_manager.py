"""브라우저 세션 관리 모듈

각 서비스(Claude, ChatGPT, Typecast, CapCut)의 로그인 세션을
persistent context로 유지합니다. 최초 1회만 수동 로그인하면
이후에는 자동으로 세션이 유지됩니다.
"""

import os
from playwright.sync_api import sync_playwright, BrowserContext, Page
import config


class BrowserManager:
    """Playwright 브라우저 세션을 관리합니다."""

    def __init__(self):
        self._playwright = None
        self._context: BrowserContext | None = None

    def start(self) -> BrowserContext:
        """브라우저를 시작하고 persistent context를 반환합니다."""
        profile_dir = os.path.abspath(config.BROWSER_PROFILE_DIR)
        os.makedirs(profile_dir, exist_ok=True)

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=config.HEADLESS,
            slow_mo=config.SLOW_MO,
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )
        return self._context

    def new_page(self) -> Page:
        """새 탭을 엽니다."""
        if not self._context:
            self.start()
        return self._context.new_page()

    def close(self):
        """브라우저를 종료합니다."""
        if self._context:
            self._context.close()
        if self._playwright:
            self._playwright.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()


def ensure_login(page: Page, service_url: str, service_name: str):
    """서비스에 로그인 상태인지 확인하고, 아니면 사용자에게 수동 로그인을 요청합니다."""
    page.goto(service_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # 로그인 페이지로 리다이렉트되었는지 간단 확인
    current_url = page.url.lower()
    login_keywords = ["login", "signin", "sign-in", "auth", "accounts"]

    if any(kw in current_url for kw in login_keywords):
        print(f"\n{'='*50}")
        print(f"  {service_name} 로그인이 필요합니다!")
        print(f"  브라우저 창에서 직접 로그인해주세요.")
        print(f"  로그인 완료 후 Enter를 눌러주세요.")
        print(f"{'='*50}\n")
        input("  → 로그인 완료 후 Enter: ")
        page.wait_for_timeout(2000)
