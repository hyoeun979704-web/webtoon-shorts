"""ChatGPT를 사용한 이미지 프롬프트 최적화 + DALL-E 이미지 생성 모듈

2단계로 동작합니다:
  1단계: ChatGPT 프로젝트에 대본을 전송 → K-Webtoon 스타일 최적화 프롬프트 수령
  2단계: 새 ChatGPT 대화에서 최적화된 프롬프트로 DALL-E 이미지 생성

프로젝트의 visual_identity/mandatory_keywords 등이 프롬프트에 자동 반영되므로
일관된 K-Webtoon 스타일이 유지됩니다.
"""

import os
import re

import requests
from playwright.sync_api import Page

import config
from browser_manager import ensure_login
from utils import log, navigate_to_project, send_and_wait, wait_for_response_complete


# ──────────────────────────────────────────────
# 1단계: 프롬프트 최적화 (ChatGPT 프로젝트)
# ──────────────────────────────────────────────

def optimize_prompts(
    page: Page,
    scenes: list[dict],
    project_url: str,
) -> list[dict]:
    """ChatGPT 프로젝트에서 이미지 프롬프트를 K-Webtoon 스타일로 최적화합니다.

    Args:
        page: 브라우저 페이지
        scenes: 구조화된 장면 목록 (scene_number, narration, cuts 포함)
        project_url: ChatGPT 프로젝트 URL

    Returns:
        최적화된 프롬프트가 반영된 scenes 리스트
    """
    ensure_login(page, config.CHATGPT_URL, "ChatGPT")
    navigate_to_project(page, config.CHATGPT_URL, project_url)

    # 대본 텍스트 구성
    script_lines = []
    cut_labels = []
    for scene in scenes:
        narration = scene.get("narration", "")
        for cut in scene.get("cuts", []):
            label = f"장면{scene['scene_number']}-컷{cut['cut_number']}"
            cut_labels.append(label)
            existing_prompt = cut.get("image_prompt", "")
            if existing_prompt:
                script_lines.append(f"[{label}] 나레이션: {narration}\n참고 프롬프트: {existing_prompt}")
            else:
                script_lines.append(f"[{label}] 나레이션: {narration}")

    prompt = (
        f"다음 숏폼 대본의 각 컷에 대해 이미지 프롬프트를 작성해주세요.\n\n"
        f"★ 필수 캐릭터 규칙: 주인공은 반드시 20대 청순하고 섹시한 한국 여성이어야 합니다. "
        f"부드럽고 섬세한 이목구비, 큰 눈, 글로시한 입술, 슬림한 몸매, 젊고 빛나는 외모. 절대 남성으로 그리지 마세요.\n"
        f"의상은 세련되고 은근히 섹시한 스타일로. "
        f"모든 프롬프트에 'beautiful Korean woman in her 20s, innocent yet alluring, delicate features, large expressive eyes, glossy lips, slim figure, stylish subtly revealing outfit'를 포함해주세요.\n\n"
        f"{chr(10).join(script_lines)}\n\n"
        f"장면 수: {len(cut_labels)}개\n\n"
        f"각 컷마다 아래 형식으로 출력해주세요:\n"
        f"[장면X-컷Y]\n"
        f"english_prompt: ...\n"
    )

    log.info("프로젝트에 프롬프트 최적화 요청 중 (%d컷)...", len(cut_labels))
    response = send_and_wait(page, prompt, timeout_sec=300)

    # 디버깅용 저장
    _save_debug("last_prompt_optimization.txt", response)

    # 응답에서 최적화된 프롬프트 파싱
    optimized = _parse_optimized_prompts(response, cut_labels)

    if not optimized:
        log.warning("프롬프트 최적화 응답 파싱 실패. 기존 프롬프트를 유지합니다.")
        return scenes

    # scenes에 최적화된 프롬프트 반영
    idx = 0
    updated = 0
    for scene in scenes:
        for cut in scene.get("cuts", []):
            label = f"장면{scene['scene_number']}-컷{cut['cut_number']}"
            if label in optimized:
                cut["image_prompt"] = optimized[label]
                updated += 1
            elif idx < len(optimized):
                # 라벨 매칭 실패 시 순서대로 할당
                values = list(optimized.values())
                if idx < len(values):
                    cut["image_prompt"] = values[idx]
                    updated += 1
            idx += 1

    log.info("프롬프트 최적화 완료: %d/%d컷 업데이트", updated, len(cut_labels))
    return scenes


def _parse_optimized_prompts(response: str, cut_labels: list[str]) -> dict:
    """프로젝트 응답에서 컷별 영문 프롬프트를 추출합니다.

    Returns:
        {"장면1-컷1": "english prompt...", ...}
    """
    result = {}

    # 패턴 1: [장면X-컷Y] + english_prompt: ...
    pattern1 = re.compile(
        r"\[장면(\d+)[-\s]*컷(\d+)\].*?english[_\s]*prompt\s*[:：]\s*(.+?)(?=\[장면|\Z|korean|self[_\s]*review|---)",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern1.finditer(response):
        label = f"장면{m.group(1)}-컷{m.group(2)}"
        prompt_text = m.group(3).strip().strip('"').strip("'").strip()
        # 여러 줄이면 첫 번째 의미있는 블록만
        lines = [l.strip() for l in prompt_text.split("\n") if l.strip()]
        if lines:
            # korean_description이나 self_review가 섞여있으면 제거
            clean_lines = []
            for line in lines:
                if re.match(r"(korean|self[_\s]*review|점수|합계)", line, re.IGNORECASE):
                    break
                clean_lines.append(line)
            result[label] = " ".join(clean_lines).strip().rstrip(",")

    if result:
        return result

    # 패턴 2: 장면X-컷Y 뒤에 영어 프롬프트가 바로 따라오는 경우
    pattern2 = re.compile(
        r"장면\s*(\d+)\s*[-–]\s*컷\s*(\d+).*?\n\s*([A-Za-z][\w\s,.'\"!:;/()-]+(?:\n[A-Za-z][\w\s,.'\"!:;/()-]+)*)",
    )
    for m in pattern2.finditer(response):
        label = f"장면{m.group(1)}-컷{m.group(2)}"
        prompt_text = m.group(3).strip()
        if len(prompt_text) > 20:
            result[label] = prompt_text

    if result:
        return result

    # 패턴 3: 번호 매칭 - "1.", "2." 등 + 영어 프롬프트
    pattern3 = re.compile(
        r"(?:^|\n)\s*\d+[\.\)]\s*([A-Za-z][\w\s,.'\"!:;/()-]{30,})",
    )
    matches = pattern3.findall(response)
    for i, prompt_text in enumerate(matches):
        if i < len(cut_labels):
            result[cut_labels[i]] = prompt_text.strip()

    return result


def _save_debug(filename: str, content: str) -> None:
    """디버깅용 파일 저장."""
    debug_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ──────────────────────────────────────────────
# 2단계: DALL-E 이미지 생성 (새 대화)
# ──────────────────────────────────────────────

def _find_all_images_js(page: Page) -> list[dict]:
    """페이지 내 모든 실질적 이미지를 찾습니다.

    naturalWidth/naturalHeight를 사용하여 viewport 밖 이미지도 정확히 감지합니다.
    (getBoundingClientRect는 스크롤 밖이면 0을 반환할 수 있어 누락 발생)

    Returns:
        [{"src": "...", "width": ..., "height": ..., "msgIndex": ...}, ...]
    """
    try:
        return page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();

                function collectImages(container, msgIdx) {
                    container.querySelectorAll('img').forEach(img => {
                        const src = img.src || img.getAttribute('src') || '';
                        // naturalWidth/Height: 원본 이미지 크기 (viewport 무관)
                        // getBoundingClientRect: 현재 표시 크기 (보이면 사용)
                        const nw = img.naturalWidth || 0;
                        const nh = img.naturalHeight || 0;
                        const rect = img.getBoundingClientRect();
                        const w = rect.width || nw;
                        const h = rect.height || nh;
                        // 아이콘/아바타 제외 (80px 이상만), 중복 제거
                        if (w > 80 && h > 80 && src && !seen.has(src)) {
                            seen.add(src);
                            results.push({
                                src: src,
                                width: Math.round(w),
                                height: Math.round(h),
                                msgIndex: msgIdx,
                            });
                        }
                    });
                }

                // 전체 페이지에서 큰 이미지 탐색 (컨테이너 제한 없이)
                collectImages(document.body, 0);

                return results;
            }
        """)
    except Exception as e:
        log.debug("JS 이미지 탐색 실패: %s", e)
        return []


def _get_image_srcs(page: Page) -> set[str]:
    """현재 페이지의 모든 큰 이미지 src를 set으로 반환합니다."""
    images = _find_all_images_js(page)
    return {img["src"] for img in images if img.get("src")}


def _wait_for_new_image(
    page: Page,
    prev_srcs: set[str],
    timeout_sec: int = 0,
) -> tuple:
    """ChatGPT 응답 완료 후 새 이미지를 찾아 반환합니다.

    이전 이미지 src 집합과 비교하여 새 이미지를 감지합니다.
    (카운트 비교보다 안정적 - 스크롤로 이전 이미지가 사라져도 영향 없음)

    무제한 대기하며 2분마다 로그를 출력합니다.

    Returns:
        (img_src, img_element) 튜플, 실패 시 (None, None)
    """
    # 1단계: 응답 완료 대기
    wait_for_response_complete(page, timeout_sec=600)

    # 2단계: 이미지 탐색 (무제한, 2분 간격 로그)
    check_interval = 120  # 2분마다 로그
    elapsed = 0
    while True:
        # JS 기반 감지
        images = _find_all_images_js(page)
        current_srcs = {img["src"] for img in images if img.get("src")}
        new_srcs = current_srcs - prev_srcs

        if new_srcs:
            page.wait_for_timeout(2000)  # 렌더링 안정화

            # 새 이미지 중 마지막 것 선택
            new_src = None
            for img in reversed(images):
                if img.get("src") in new_srcs:
                    new_src = img["src"]
                    log.info("    새 이미지 감지: %dx%d, src=%s...",
                             img["width"], img["height"], new_src[:60])
                    break

            img_element = _get_last_assistant_image(page)
            return new_src, img_element

        # Playwright locator 폴백: JS가 이미지를 못 찾는 경우
        try:
            all_imgs = page.locator("img").all()
            for img in reversed(all_imgs):
                try:
                    src = img.get_attribute("src") or ""
                    if not src or src in prev_srcs:
                        continue
                    # naturalWidth로 크기 확인 (viewport 무관)
                    size = img.evaluate("el => ({w: el.naturalWidth, h: el.naturalHeight})")
                    if size["w"] > 80 and size["h"] > 80:
                        page.wait_for_timeout(2000)
                        log.info("    새 이미지 감지(Playwright): src=%s...", src[:60])
                        return src, img
                except Exception:
                    continue
        except Exception:
            pass

        # 10초 대기 후 재체크
        page.wait_for_timeout(10000)
        elapsed += 10

        if elapsed > 0 and elapsed % check_interval == 0:
            log.info("    이미지 생성 대기 중... (%d분 경과)", elapsed // 60)

        if timeout_sec > 0 and elapsed >= timeout_sec:
            break

    return None, None


def _get_last_assistant_image(page: Page):
    """마지막 어시스턴트 메시지에서 마지막 큰 이미지 요소를 반환합니다."""
    # 여러 컨테이너 셀렉터 순서대로 시도
    container_selectors = [
        'article.agent-turn',
        '[data-message-author-role="assistant"]',
        'article[data-testid*="conversation-turn"]',
        'div[class*="agent-turn"]',
    ]
    for sel in container_selectors:
        try:
            container = page.locator(sel).last
            if container.count() == 0:
                continue
            imgs = container.locator("img").all()
            for img in reversed(imgs):
                try:
                    bbox = img.bounding_box()
                    if bbox and bbox["width"] > 80 and bbox["height"] > 80:
                        return img
                except Exception:
                    continue
        except Exception:
            continue

    # 폴백: 페이지 전체에서 마지막 큰 이미지
    imgs = page.locator("img").all()
    for img in reversed(imgs):
        try:
            bbox = img.bounding_box()
            if bbox and bbox["width"] > 80 and bbox["height"] > 80:
                return img
        except Exception:
            continue

    return None


def _click_download_button(page: Page, img_element, output_path: str) -> bool:
    """ChatGPT 이미지의 다운로드 버튼을 클릭하여 원본 이미지를 저장합니다.

    이미지에 호버하면 나타나는 다운로드 버튼을 클릭하고,
    Playwright의 download 이벤트를 캡처하여 지정 경로에 저장합니다.

    Returns:
        성공 여부
    """
    if not img_element:
        return False

    try:
        # 이미지 위에 호버하여 오버레이 버튼 표시
        img_element.hover()
        page.wait_for_timeout(1000)

        # 다운로드 버튼 찾기 (여러 셀렉터 시도)
        download_btn_selectors = [
            'a[download]',                                  # <a download> 속성
            'button[aria-label*="download" i]',             # Download / download
            'button[aria-label*="save" i]',                 # Save image
            'button[aria-label*="다운로드"]',
            '[role="button"][aria-label*="download" i]',
            'button[data-testid="download-button"]',
        ]

        # 이미지의 부모 컨테이너에서 다운로드 버튼 탐색
        # ChatGPT는 article.agent-turn 또는 div.group/relative 안에 이미지를 렌더링
        container_selectors = [
            "xpath=ancestor::article[contains(@class, 'agent-turn')]",
            "xpath=ancestor::div[contains(@class, 'group') or contains(@class, 'relative')]",
        ]
        download_btn = None

        for cont_sel in container_selectors:
            container = img_element.locator(cont_sel).first
            if container.count() == 0:
                continue

            for sel in download_btn_selectors:
                btn = container.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    download_btn = btn
                    break

            # SVG 다운로드 아이콘 버튼 탐색
            if not download_btn:
                # a 태그와 button 태그 모두 탐색
                clickables = container.locator("a, button, [role='button'], [role='menuitem']").all()
                for btn in clickables:
                    try:
                        if not btn.is_visible():
                            continue
                        # aria-label, title, innerText에서 download/save 키워드 확인
                        aria = (btn.get_attribute("aria-label") or "").lower()
                        title = (btn.get_attribute("title") or "").lower()
                        text = btn.inner_text().lower().strip()
                        has_download_attr = btn.get_attribute("download") is not None
                        if has_download_attr or "download" in aria or "save" in aria or "download" in title or "download" in text:
                            download_btn = btn
                            break
                    except Exception:
                        continue

            if download_btn:
                break

        # 컨테이너에서 못 찾으면 마지막 어시스턴트 메시지/agent-turn에서 탐색
        if not download_btn:
            fallback_containers = [
                page.locator('article.agent-turn').last,
                page.locator('[data-message-author-role="assistant"]').last,
            ]
            for fb in fallback_containers:
                try:
                    if fb.count() == 0:
                        continue
                    for sel in download_btn_selectors:
                        btn = fb.locator(sel).first
                        if btn.count() > 0 and btn.is_visible():
                            download_btn = btn
                            break
                    if download_btn:
                        break
                except Exception:
                    continue

        if not download_btn:
            log.debug("    다운로드 버튼을 찾을 수 없습니다")
            return False

        # Playwright download 이벤트 캡처 후 버튼 클릭
        with page.expect_download(timeout=30000) as download_info:
            download_btn.click()

        download = download_info.value
        download.save_as(output_path)
        size = os.path.getsize(output_path)
        log.info("    다운로드 버튼으로 저장 완료: %s (%d KB)",
                 os.path.basename(output_path), size // 1024)
        return True

    except Exception as e:
        log.debug("    다운로드 버튼 방식 실패: %s", e)
        return False


def _download_image(page: Page, img_src: str, img_element, output_path: str) -> None:
    """이미지를 다운로드합니다. 다운로드 버튼 → URL → 스크린샷 순으로 시도합니다."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 방법 1: ChatGPT 다운로드 버튼 클릭 (원본 품질)
    if _click_download_button(page, img_element, output_path):
        return

    # 방법 2: HTTP URL 직접 다운로드
    if img_src and img_src.startswith("http"):
        try:
            resp = requests.get(img_src, timeout=60)
            resp.raise_for_status()
            if len(resp.content) > 1000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                log.info("    URL 다운로드 저장: %s (%d KB)",
                         os.path.basename(output_path), len(resp.content) // 1024)
                return
            log.warning("    다운로드 이미지가 너무 작습니다 (%d bytes)", len(resp.content))
        except Exception as e:
            log.warning("    URL 다운로드 실패: %s", e)

    # 방법 3: 이미지 요소 스크린샷
    if img_element:
        try:
            if img_element.is_visible():
                img_element.screenshot(path=output_path)
                size = os.path.getsize(output_path)
                log.info("    스크린샷 저장: %s (%d KB)", os.path.basename(output_path), size // 1024)
                return
        except Exception as e:
            log.warning("    이미지 스크린샷 실패: %s", e)

    # 방법 4: 마지막 어시스턴트 메시지 전체 스크린샷
    try:
        last_msg = page.locator('[data-message-author-role="assistant"]').last
        if last_msg.is_visible():
            last_msg.screenshot(path=output_path)
            log.warning("    메시지 전체 스크린샷으로 대체 저장")
            return
    except Exception:
        pass

    raise RuntimeError(f"이미지를 저장할 수 없습니다: {output_path}")


def _send_image_prompt(page: Page, prompt: str) -> None:
    """ChatGPT 입력창에 이미지 생성 프롬프트를 전송합니다.

    프로젝트에서 최적화된 프롬프트를 그대로 사용합니다.
    """
    # 주인공 캐릭터 일관성 강제: 20대 청순하고 섹시한 한국 여성
    character_directive = (
        "MANDATORY CHARACTER RULE: The main character (protagonist) MUST be "
        "a beautiful Korean woman in her 20s with an innocent yet alluring look. "
        "She has delicate soft facial features, large expressive eyes, "
        "glossy lips, slim figure, and a youthful radiant appearance. "
        "Her outfit should be stylish and subtly revealing — showing elegance with a hint of sexiness. "
        "She must NEVER be depicted as male. "
    )
    full_prompt = (
        f"{character_directive}\n\n"
        f"Generate a single image with the following description. "
        f"Style: K-Webtoon / manhwa digital illustration, vertical 9:16 portrait, "
        f"cinematic lighting, high detail, clean lines, vibrant colors.\n\n"
        f"{prompt}\n\n"
        f"IMPORTANT: No text, letters, words, or speech bubbles in the image."
    )

    editor = page.locator("#prompt-textarea, [contenteditable='true']").first
    editor.wait_for(timeout=10000)
    editor.click()
    editor.fill(full_prompt)
    page.wait_for_timeout(500)

    send_btn = page.locator('[data-testid="send-button"]').first
    if send_btn.is_visible():
        send_btn.click()
    else:
        editor.press("Enter")


def init_image_session(page: Page, project_url: str = "") -> None:
    """ChatGPT 이미지 생성 세션을 시작합니다 (프로젝트 이동 + 로그인).

    프로젝트 URL이 주어지면 해당 프로젝트로 이동하여
    프로젝트에 설정된 스타일 지침이 이미지 생성에 반영됩니다.
    """
    ensure_login(page, config.CHATGPT_URL, "ChatGPT")
    navigate_to_project(page, config.CHATGPT_URL, project_url)


def generate_image_in_session(
    page: Page,
    prompt: str,
    output_path: str,
) -> str:
    """이미 열린 ChatGPT 대화에서 이미지를 생성합니다.

    무제한 대기하며 이미지가 생성될 때까지 기다립니다.
    이미지 감지에 실패해도 스크린샷 폴백으로 반드시 저장합니다.
    """
    prev_srcs = _get_image_srcs(page)

    _send_image_prompt(page, prompt)

    log.info("    이미지 생성 대기 중...")
    img_src, img_element = _wait_for_new_image(page, prev_srcs)

    if img_src or img_element:
        try:
            _download_image(page, img_src, img_element, output_path)
            return output_path
        except Exception as e:
            log.warning("    이미지 다운로드 실패, 스크린샷 폴백: %s", e)

    # 폴백: 페이지에서 마지막 큰 이미지 요소를 직접 찾아서 스크린샷
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fallback_img = _get_last_assistant_image(page)
    if fallback_img:
        try:
            fallback_img.screenshot(path=output_path)
            size = os.path.getsize(output_path)
            log.info("    스크린샷 폴백 저장: %s (%d KB)",
                     os.path.basename(output_path), size // 1024)
            return output_path
        except Exception as e:
            log.warning("    스크린샷 폴백 실패: %s", e)

    # 최종 폴백: 대화 영역 전체 스크린샷
    try:
        main_area = page.locator("main").first
        if main_area.is_visible():
            main_area.screenshot(path=output_path)
            log.warning("    대화 영역 전체 스크린샷으로 대체 저장")
            return output_path
    except Exception:
        pass

    raise RuntimeError(f"이미지를 저장할 수 없습니다: {output_path}")
