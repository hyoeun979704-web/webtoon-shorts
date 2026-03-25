"""브라우저 세션 관리 모듈

각 서비스(ChatGPT, CapCut)의 로그인 세션을
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
            // ── navigator.webdriver 완전 제거 ──
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true,
            });
            // Proxy를 사용해 prototype 체인에서도 숨김
            const origGet = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
            if (origGet) {
                Object.defineProperty(Navigator.prototype, 'webdriver', {
                    get: () => undefined,
                    configurable: true,
                });
            }

            // ── chrome.runtime 속성 추가 (일반 Chrome/Edge처럼 보이게) ──
            window.chrome = window.chrome || {};
            window.chrome.runtime = window.chrome.runtime || {
                connect: function() {},
                sendMessage: function() {},
            };
            window.chrome.csi = window.chrome.csi || function() { return {}; };
            window.chrome.loadTimes = window.chrome.loadTimes || function() { return {}; };

            // ── Permissions API 감지 우회 ──
            const origQuery = window.navigator.permissions?.query;
            if (origQuery) {
                window.navigator.permissions.query = (params) => {
                    if (params.name === 'notifications') {
                        return Promise.resolve({ state: Notification.permission });
                    }
                    return origQuery.call(window.navigator.permissions, params);
                };
            }

            // ── plugins 배열 위장 (빈 배열이면 headless로 감지됨) ──
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' },
                ],
                configurable: true,
            });

            // ── mimeTypes 위장 ──
            Object.defineProperty(navigator, 'mimeTypes', {
                get: () => [
                    { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
                ],
                configurable: true,
            });

            // ── languages 위장 ──
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ko-KR', 'ko', 'en-US', 'en'],
                configurable: true,
            });

            // ── Automation-related CDP 속성 제거 ──
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

            // ── WebGL vendor/renderer 위장 ──
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Google Inc. (ANGLE)';  // UNMASKED_VENDOR_WEBGL
                if (param === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics, OpenGL 4.1)';
                return getParameter.call(this, param);
            };

            // ── iframe contentWindow 접근 시 감지 방지 ──
            const origAttachShadow = Element.prototype.attachShadow;
            Element.prototype.attachShadow = function() {
                return origAttachShadow.call(this, ...arguments);
            };
        """)
    except Exception:
        pass  # 이미 닫힌 페이지 등


def _try_click_turnstile(page: Page) -> bool:
    """Cloudflare Turnstile iframe 안의 체크박스를 자동 클릭 시도합니다."""
    try:
        # Turnstile iframe 찾기
        iframe_selectors = [
            'iframe[src*="challenges.cloudflare.com"]',
            'iframe[src*="turnstile"]',
            'iframe[title*="Cloudflare"]',
            'iframe[title*="challenge"]',
        ]
        for sel in iframe_selectors:
            try:
                iframe_el = page.locator(sel).first
                if not iframe_el.is_visible(timeout=500):
                    continue
                frame = iframe_el.content_frame()
                if not frame:
                    continue

                # iframe 내부의 체크박스/버튼 클릭
                click_targets = [
                    'input[type="checkbox"]',
                    '#challenge-stage input',
                    '.cb-lb',  # Turnstile checkbox label
                    'label',
                    'body',  # 마지막 수단: iframe body 클릭
                ]
                for target in click_targets:
                    try:
                        el = frame.locator(target).first
                        if el.is_visible(timeout=300):
                            el.click()
                            log.info("  Turnstile 체크박스 클릭 시도: %s", target)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue

        # iframe 접근 불가 시, 페이지 내 Turnstile 요소 직접 클릭
        direct_targets = [
            '#turnstile-wrapper',
            '[class*="turnstile"]',
            '.cf-turnstile',
        ]
        for sel in direct_targets:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=300):
                    # 요소 중앙 클릭
                    box = el.bounding_box()
                    if box:
                        page.mouse.click(
                            box["x"] + box["width"] / 2,
                            box["y"] + box["height"] / 2,
                        )
                        log.info("  Turnstile 요소 클릭 시도: %s", sel)
                        return True
            except Exception:
                continue

    except Exception as e:
        log.debug("  Turnstile 자동 클릭 실패: %s", e)
    return False


def _wait_for_captcha(page: Page, service_name: str) -> None:
    """Cloudflare Turnstile/CAPTCHA 페이지가 감지되면 자동 통과를 대기합니다.

    1단계: 자동 통과 대기 (실제 브라우저 사용 시 대부분 자동 통과)
    2단계: Turnstile 체크박스 자동 클릭 시도
    3단계: 수동 완료 요청
    """
    def _is_challenge_page() -> bool:
        """현재 페이지가 Cloudflare 챌린지 등 확인 페이지인지 판단합니다."""
        try:
            url = page.url.lower()
            if "challenges.cloudflare.com" in url:
                return True

            title = page.title().lower()
            if any(kw in title for kw in ("just a moment", "확인 중", "attention required")):
                return True

            for sel in (
                'iframe[src*="challenges.cloudflare.com"]',
                '#challenge-running',
                '#challenge-stage',
                '#turnstile-wrapper',
                'iframe[src*="turnstile"]',
            ):
                try:
                    if page.locator(sel).first.is_visible(timeout=500):
                        return True
                except Exception:
                    pass

            try:
                body_text = page.locator("body").first.inner_text(timeout=1000)
                if len(body_text) < 300 and any(
                    kw in body_text for kw in ("Verify you are human", "사람인지 확인",
                                                 "보안 확인 수행 중", "확인하는 중",
                                                 "확인 중", "Just a moment")
                ):
                    return True
            except Exception:
                pass

        except Exception:
            pass
        return False

    if not _is_challenge_page():
        return

    log.info("  %s: Cloudflare 보안 확인 감지. 자동 통과 대기 중...", service_name)

    clicked = False
    for elapsed in range(120):
        page.wait_for_timeout(1000)

        if not _is_challenge_page():
            log.info("  보안 확인 통과! (%d초)", elapsed + 1)
            page.wait_for_timeout(2000)
            return

        # 5초, 10초, 20초에 체크박스 자동 클릭 시도
        if not clicked and elapsed in (5, 10, 20, 40):
            if _try_click_turnstile(page):
                clicked = True

        if elapsed > 0 and elapsed % 30 == 0:
            # 30초 경과 시 재시도
            _try_click_turnstile(page)
            log.warning("  아직 확인 중... 브라우저에서 체크박스가 있으면 클릭해주세요. (%d초)", elapsed)

    # 타임아웃 → 수동 완료 요청
    log.warning("")
    log.warning("=" * 50)
    log.warning("  %s Cloudflare 보안 확인을 자동 통과하지 못했습니다.", service_name)
    log.warning("  브라우저에서 직접 완료 후 Enter를 눌러주세요.")
    log.warning("=" * 50)
    input("  → 확인 완료 후 Enter: ")
    page.wait_for_timeout(2000)


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
                # 실제 설치된 브라우저(Edge/Chrome) 사용으로 Cloudflare 우회
                channel = getattr(config, "BROWSER_CHANNEL", "msedge")
                launch_kwargs = dict(
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
                        "--disable-dev-shm-usage",
                    ],
                    ignore_default_args=["--enable-automation"],
                )
                if channel and channel != "chromium":
                    launch_kwargs["channel"] = channel
                    log.info("  브라우저 채널: %s (실제 설치된 브라우저 사용)", channel)

                self._context = self._playwright.chromium.launch_persistent_context(
                    **launch_kwargs
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
