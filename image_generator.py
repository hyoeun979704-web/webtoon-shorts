"""OpenAI DALL-E API 기반 이미지 생성 모듈

구조화된 대본의 각 컷별 이미지 프롬프트로 DALL-E 이미지를 생성합니다.
(병렬 처리 적용)
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai_client import generate_image
from utils import log


def generate_images(
    structured: dict,
    images_dir: str,
    image_style: str = "",
) -> tuple[list[str], list[str]]:
    """구조화된 대본의 모든 컷에 대해 이미지를 생성합니다.

    Returns:
        (성공 경로 리스트, 실패 컷 라벨 리스트)
    """
    os.makedirs(images_dir, exist_ok=True)

    total_cuts = sum(len(s.get("cuts", [])) for s in structured["scenes"])
    image_paths = []
    failed_cuts = []

    tasks = []

    img_idx = 0
    for scene in structured["scenes"]:
        for cut in scene.get("cuts", []):
            img_idx += 1
            prompt = cut.get("image_prompt", "").strip()
            if not prompt:
                log.warning("  장면%d-컷%d: 이미지 프롬프트 없음, 건너뜀",
                            scene["scene_number"], cut["cut_number"])
                continue

            output_path = os.path.join(
                images_dir,
                f"s{scene['scene_number']:02d}_c{cut['cut_number']:02d}.png",
            )

            # 이미 생성된 이미지가 있으면 건너뛰기
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                log.info("  [%d/%d] 장면%d-컷%d 이미 존재, 건너뜀",
                         img_idx, total_cuts,
                         scene["scene_number"], cut["cut_number"])
                image_paths.append(output_path)
                continue

            # 레이아웃 강제 고정 및 2D 애니메이션 스타일 주입 (화면 분할 철저히 방지 및 3D 렌더링 방지)
            layout_prefix = "A single unbroken vertical illustration piece that completely fills the canvas seamlessly. Traditional 2D Japanese Anime aesthetic, high-quality flat cel shading, Kyoto Animation style, soft luminous pastel colors. NOT 3D, NO CGI, NO realistic, NO comic panels. "
            style_prefix = image_style + ", " if (image_style and image_style.lower() not in prompt.lower()) else ""
            prompt = f"{layout_prefix}{style_prefix}{prompt}"

            tasks.append({
                "scene": scene["scene_number"],
                "cut": cut["cut_number"],
                "prompt": prompt,
                "output_path": output_path,
                "idx": img_idx,
            })

    if not tasks:
        return image_paths, failed_cuts

    log.info("  => %d컷에 대해 순차적 이미지 생성을 시작합니다...", len(tasks))

    for t in tasks:
        log.info("  [%d/%d] 장면%d-컷%d 이미지 생성 중...",
                 t["idx"], total_cuts, t["scene"], t["cut"])
        try:
            result = generate_image(
                prompt=t["prompt"],
                output_path=t["output_path"],
                size="1024x1792",  # 세로 9:16
            )
            cut_label = f"장면{t['scene']}-컷{t['cut']}"
            if result:
                image_paths.append(t["output_path"])
                log.info("  %s 저장 완료: %s", cut_label, os.path.basename(t["output_path"]))
            else:
                failed_cuts.append(cut_label)
                log.warning("  %s 이미지 생성/저장 실패", cut_label)
        except Exception as e:
            cut_label = f"장면{t['scene']}-컷{t['cut']}"
            failed_cuts.append(cut_label)
            log.warning("  %s 이미지 생성 중 예외 발생: %s", cut_label, str(e))

    return image_paths, failed_cuts
