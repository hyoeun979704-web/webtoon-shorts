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
        f"★ 필수 캐릭터 규칙: 주인공은 반드시 20대 예쁘고 귀여운 한국 여성이어야 합니다. "
        f"부드러운 이목구비, 큰 눈, 젊고 사랑스러운 외모. 절대 남성으로 그리지 마세요.\n"
        f"모든 프롬프트에 'pretty cute Korean woman in her 20s, soft features, large expressive eyes'를 포함해주세요.\n\n"
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
    """JavaScript로 어시스턴트 메시지 내 모든 실질적 이미지를 찾습니다.

    Returns:
        [{"src": "...", "width": ..., "height": ..., "msgIndex": ...}, ...]
    """
    try:
        return page.evaluate("""
            () => {
                const results = [];
                // 어시스턴트 메시지 탐색
                const msgs = document.querySelectorAll(
                    '[data-message-author-role="assistant"]'
                );
                msgs.forEach((msg, msgIdx) => {
                    msg.querySelectorAll('img').forEach(img => {
                        const rect = img.getBoundingClientRect();
                        const src = img.src || img.getAttribute('src') || '';
                        // 아이콘/아바타 제외 (80px 이상만)
                        if (rect.width > 80 && rect.height > 80 && src) {
                            results.push({
                                src: src,
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                msgIndex: msgIdx,
                            });
                        }
                    });
                });
                return results;
            }
        """)
    except Exception as e:
        log.debug("JS 이미지 탐색 실패: %s", e)
        return []


def _wait_for_new_image(
    page: Page,
    prev_count: int,
    timeout_sec: int = 300,
) -> tuple:
    """ChatGPT 응답 완료 후 새 이미지를 찾아 반환합니다.

    Returns:
        (img_src, img_element) 튜플
    """
    # 1단계: 응답 완료 대기
    wait_for_response_complete(page, timeout_sec=timeout_sec)

    # 2단계: 이미지 탐색 (최대 90초 추가 대기)
    for retry in range(90):
        images = _find_all_images_js(page)
        if len(images) > prev_count:
            page.wait_for_timeout(2000)  # 렌더링 안정화

            # 새로운 이미지의 src 가져오기
            new_img_info = images[-1]
            src = new_img_info["src"]
            log.info("    새 이미지 감지: %dx%d, src=%s...",
                     new_img_info["width"], new_img_info["height"], src[:60])

            # 해당 이미지 요소 참조
            img_element = _get_last_assistant_image(page)
            return src, img_element

        page.wait_for_timeout(1000)
        if retry > 0 and retry % 15 == 0:
            log.info("    이미지 렌더링 대기 중... (%d초)", retry)

    raise TimeoutError(
        f"ChatGPT 이미지를 찾을 수 없습니다. "
        f"이전 이미지 수: {prev_count}, 현재: {len(_find_all_images_js(page))}"
    )


def _get_last_assistant_image(page: Page):
    """마지막 어시스턴트 메시지에서 마지막 큰 이미지 요소를 반환합니다."""
    try:
        last_msg = page.locator('[data-message-author-role="assistant"]').last
        imgs = last_msg.locator("img").all()
        # 큰 이미지만 필터링
        for img in reversed(imgs):
            try:
                bbox = img.bounding_box()
                if bbox and bbox["width"] > 80 and bbox["height"] > 80:
                    return img
            except Exception:
                continue
    except Exception:
        pass

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


def _download_image(page: Page, img_src: str, img_element, output_path: str) -> None:
    """이미지를 다운로드합니다. URL 실패 시 스크린샷으로 대체합니다."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 방법 1: HTTP URL 직접 다운로드
    if img_src and img_src.startswith("http"):
        try:
            resp = requests.get(img_src, timeout=60)
            resp.raise_for_status()
            if len(resp.content) > 1000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                log.info("    저장 완료: %s (%d KB)",
                         os.path.basename(output_path), len(resp.content) // 1024)
                return
            log.warning("    다운로드 이미지가 너무 작습니다 (%d bytes)", len(resp.content))
        except Exception as e:
            log.warning("    URL 다운로드 실패: %s", e)

    # 방법 2: 이미지 요소 스크린샷
    if img_element:
        try:
            if img_element.is_visible():
                img_element.screenshot(path=output_path)
                size = os.path.getsize(output_path)
                log.info("    스크린샷 저장: %s (%d KB)", os.path.basename(output_path), size // 1024)
                return
        except Exception as e:
            log.warning("    이미지 스크린샷 실패: %s", e)

    # 방법 3: 마지막 어시스턴트 메시지 전체 스크린샷
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
    # 주인공 캐릭터 일관성 강제: 20대 예쁘고 귀여운 한국 여성
    character_directive = (
        "MANDATORY CHARACTER RULE: The main character (protagonist) MUST be "
        "a pretty and cute Korean woman in her 20s with soft facial features, "
        "large expressive eyes, and a youthful appearance. "
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

    프로젝트에서 최적화된 프롬프트를 사용하므로 스타일 일관성이 보장됩니다.
    """
    prev_count = len(_find_all_images_js(page))

    _send_image_prompt(page, prompt)

    log.info("    이미지 생성 대기 중...")
    img_src, img_element = _wait_for_new_image(page, prev_count)
    _download_image(page, img_src, img_element, output_path)

    return output_path
