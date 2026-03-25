"""브라우저 세션 관리 모듈

각 서비스(Claude, ChatGPT, CapCut)의 로그인 세션을
persistent context로 유지합니다. 최초 1회만 수동 로그인하면
이후에는 자동으로 세션이 유지됩니다.
"""

import os
import glob
import time
import subprocess
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, BrowserContext, Page
import config
from utils import log, _safe_goto


def _kill_stale_chrome(profile_dir: str) -> None:
    """해당 프로필 디렉토리를 사용 중인 Chrome 프로세스를 종료합니다."""
    if sys.platform == "win32":
        # Windows: taskkill로 chrome.exe 중 해당 프로필을 사용하는 프로세스 종료
        try:
            # wmic으로 해당 프로필을 인자로 가진 chrome 프로세스 찾기
            result = subprocess.run(
                ["wmic", "process", "where",
                 f"name='chrome.exe' and commandline like '%{os.path.basename(profile_dir)}%'",
                 "get", "processid"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.isdigit():
                    subprocess.run(["taskkill", "/F", "/PID", line],
                                   capture_output=True, timeout=10)
                    log.info("  기존 Chrome 프로세스 종료: PID %s", line)
        except Exception:
            # wmic 실패 시 전체 chrome 종료하지 않음 (안전)
            pass
    else:
        # Linux/macOS: pkill로 해당 프로필 인자를 가진 chromium 종료
        try:
            subprocess.run(
                ["pkill", "-f", f"--user-data-dir={profile_dir}"],
                capture_output=True, timeout=10
            )
        except Exception:
            pass


def _remove_lock_files(profile_dir: str) -> None:
    """Chrome 프로필의 잠금 파일을 제거합니다."""
    lock_patterns = [
        os.path.join(profile_dir, "SingletonLock"),
        os.path.join(profile_dir, "SingletonSocket"),
        os.path.join(profile_dir, "SingletonCookie"),
        os.path.join(profile_dir, "lockfile"),
    ]
    for pattern in lock_patterns:
        for lock_file in glob.glob(pattern):
            try:
                os.remove(lock_file)
                log.debug("  잠금 파일 제거: %s", lock_file)
            except Exception:
                pass


def _inject_stealth(page: Page) -> None:
    """페이지에 자동화 감지 우회 스크립트를 주입합니다."""
    try:
        page.add_init_script("""
            // navigator.webdriver 제거
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // chrome.runtime 속성 추가 (일반 Chrome처럼 보이게)
            window.chrome = window.chrome || {};
            window.chrome.runtime = window.chrome.runtime || {};

            // Permissions API 감지 우회
            const origQuery = window.navigator.permissions?.query;
            if (origQuery) {
                window.navigator.permissions.query = (params) => {
                    if (params.name === 'notifications') {
                        return Promise.resolve({ state: Notification.permission });
                    }
                    return origQuery(params);
                };
            }

            // plugins 배열 위장 (빈 배열이면 headless로 감지됨)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // languages 위장
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ko-KR', 'ko', 'en-US', 'en'],
            });
        """)
    except Exception:
        pass  # 이미 닫힌 페이지 등


def _wait_for_captcha(page: Page, service_name: str) -> None:
    """Cloudflare/reCAPTCHA 등 사람 확인 페이지가 감지되면 사용자에게 알리고 대기합니다."""
    captcha_selectors = [
        'iframe[src*="challenges.cloudflare.com"]',
        '#challenge-running',
        '#challenge-stage',
        'iframe[src*="recaptcha"]',
        'iframe[src*="hcaptcha"]',
        'div[class*="captcha"]',
        'text="Verify you are human"',
        'text="사람인지 확인"',
        'text="확인 중"',
    ]
    selector = ", ".join(captcha_selectors)

    try:
        captcha = page.locator(selector).first
        if captcha.is_visible(timeout=3000):
            log.warning("")
            log.warning("=" * 50)
            log.warning("  %s에서 사람 확인(CAPTCHA)이 감지되었습니다!", service_name)
            log.warning("  브라우저 창에서 직접 CAPTCHA를 완료해주세요.")
            log.warning("=" * 50)

            # CAPTCHA가 사라질 때까지 대기 (최대 5분)
            for _ in range(300):
                page.wait_for_timeout(1000)
                try:
                    if not captcha.is_visible():
                        log.info("  CAPTCHA 통과 완료!")
                        page.wait_for_timeout(2000)
                        return
                except Exception:
                    # 요소가 DOM에서 사라짐 = 통과
                    log.info("  CAPTCHA 통과 완료!")
                    page.wait_for_timeout(2000)
                    return

            log.warning("  CAPTCHA 대기 타임아웃. 수동으로 완료 후 Enter를 눌러주세요.")
            input("  → CAPTCHA 완료 후 Enter: ")
    except Exception:
        pass  # CAPTCHA 없으면 정상 진행


class BrowserManager:
    """Playwright 브라우저 세션을 관리합니다."""

    def __init__(self):
        self._playwright = None
        self._context: BrowserContext | None = None

    def start(self) -> BrowserContext:
        """브라우저를 시작하고 persistent context를 반환합니다.

        프로필 잠금 등으로 실패하면 잠금 해제 후 최대 2회 재시도합니다.
        """
        profile_dir = os.path.abspath(config.BROWSER_PROFILE_DIR)
        os.makedirs(profile_dir, exist_ok=True)

        self._playwright = sync_playwright().start()

        last_error = None
        for attempt in range(3):
            try:
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=config.HEADLESS,
                    slow_mo=config.SLOW_MO,
                    viewport={"width": 1280, "height": 900},
                    locale="ko-KR",
                    timezone_id="Asia/Seoul",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--no-sandbox",
                    ],
                )
                # 자동화 감지 우회: navigator.webdriver 플래그 제거
                for p in self._context.pages:
                    _inject_stealth(p)
                self._context.on("page", _inject_stealth)
                return self._context
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                if attempt < 2 and ("target closed" in error_msg or
                                    "browser has been closed" in error_msg or
                                    "crashed" in error_msg):
                    log.warning("  브라우저 시작 실패 (시도 %d/3): %s", attempt + 1, e)
                    log.info("  프로필 잠금 해제 후 재시도합니다...")
                    _kill_stale_chrome(profile_dir)
                    _remove_lock_files(profile_dir)
                    time.sleep(3)
                else:
                    break

        raise last_error

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
    _safe_goto(page, service_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Cloudflare/CAPTCHA 확인이 나오면 사용자에게 알리고 대기
    _wait_for_captcha(page, service_name)

    current_url = page.url.lower()
    login_keywords = ["login", "signin", "sign-in", "auth", "accounts"]
    needs_login = any(kw in current_url for kw in login_keywords)

    # 이미 로그인되어 있지만 계정 힌트가 있으면 확인
    if not needs_login and account_hint:
        log.info("  %s 이미 로그인됨 - 계정 확인 필요: %s", service_name, account_hint)
        reply = input(f"  → 현재 {account_hint} 계정이 맞나요? (Y/n): ").strip().lower()
        if reply in ("n", "no"):
            log.info("  %s 로그아웃 후 재로그인합니다...", service_name)
            domain = urlparse(service_url).hostname
            _clear_cookies_for_domain(page.context, domain)
            _safe_goto(page, service_url, wait_until="domcontentloaded", timeout=30000)
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
