"""OpenAI DALL-E API 기반 이미지 생성 모듈

구조화된 대본의 각 컷별 이미지 프롬프트로 DALL-E 이미지를 생성합니다.
"""

import os

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

            log.info("  [%d/%d] 장면%d-컷%d 이미지 생성 중...",
                     img_idx, total_cuts,
                     scene["scene_number"], cut["cut_number"])

            # 이미지 스타일이 프롬프트에 없으면 추가
            if image_style and image_style.lower() not in prompt.lower():
                prompt = f"{image_style}, {prompt}"

            try:
                result = generate_image(
                    prompt=prompt,
                    output_path=output_path,
                    size="1024x1792",  # 세로 9:16
                )
                if result:
                    image_paths.append(output_path)
                    log.info("  장면%d-컷%d 저장 완료: %s",
                             scene["scene_number"], cut["cut_number"],
                             os.path.basename(output_path))
                else:
                    cut_label = f"장면{scene['scene_number']}-컷{cut['cut_number']}"
                    failed_cuts.append(cut_label)
                    log.warning("  %s 이미지 저장 실패", cut_label)
            except Exception as e:
                cut_label = f"장면{scene['scene_number']}-컷{cut['cut_number']}"
                failed_cuts.append(cut_label)
                log.error("  %s 이미지 생성 오류: %s", cut_label, e)

    return image_paths, failed_cuts
