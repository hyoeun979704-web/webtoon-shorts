"""브라우저 세션 관리 모듈

각 서비스(Claude, ChatGPT, Typecast, CapCut)의 로그인 세션을
persistent context로 유지합니다. 최초 1회만 수동 로그인하면
이후에는 자동으로 세션이 유지됩니다.
"""

import os
from playwright.sync_api import sync_playwright, BrowserContext, Page
import config
from utils import log


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
        try:
            if self._context:
                self._context.close()
        except Exception as e:
            log.warning("브라우저 컨텍스트 종료 중 오류: %s", e)
        finally:
            self._context = None

        try:
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            log.warning("Playwright 종료 중 오류: %s", e)
        finally:
            self._playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()


def _clear_cookies_for_domain(context, domain: str):
    """특정 도메인의 쿠키를 삭제합니다."""
    try:
        cookies = context.cookies()
        to_keep = [c for c in cookies if domain not in c.get("domain", "")]
        context.clear_cookies()
        if to_keep:
            context.add_cookies(to_keep)
    except Exception as e:
        log.warning("쿠키 삭제 중 오류: %s", e)


def ensure_login(page: Page, service_url: str, service_name: str, account_hint: str = ""):
    """서비스에 로그인 상태인지 확인하고, 아니면 사용자에게 수동 로그인을 요청합니다."""
    page.goto(service_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    current_url = page.url.lower()
    login_keywords = ["login", "signin", "sign-in", "auth", "accounts"]
    needs_login = any(kw in current_url for kw in login_keywords)

    # 이미 로그인되어 있지만 계정 힌트가 있으면 확인
    if not needs_login and account_hint:
        log.info("  %s 이미 로그인됨 - 계정 확인 필요: %s", service_name, account_hint)
        reply = input(f"  → 현재 {account_hint} 계정이 맞나요? (Y/n): ").strip().lower()
        if reply in ("n", "no"):
            log.info("  %s 로그아웃 후 재로그인합니다...", service_name)
            # 해당 도메인 쿠키 삭제
            from urllib.parse import urlparse
            domain = urlparse(service_url).hostname
            _clear_cookies_for_domain(page.context, domain)
            page.goto(service_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            needs_login = True

    if needs_login:
        log.info("")
        log.info("=" * 50)
        log.info("  %s 로그인이 필요합니다!", service_name)
        if account_hint:
            log.info("  → 사용할 계정: %s", account_hint)
        log.info("  브라우저 창에서 직접 로그인해주세요.")
        log.info("  로그인 완료 후 Enter를 눌러주세요.")
        log.info("=" * 50)
        input("  → 로그인 완료 후 Enter: ")
        page.wait_for_timeout(2000)

        # 로그인 후 재확인
        current_url = page.url.lower()
        if any(kw in current_url for kw in login_keywords):
            log.warning("로그인 페이지에서 벗어나지 못했습니다. URL: %s", page.url)
