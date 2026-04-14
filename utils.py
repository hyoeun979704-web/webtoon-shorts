"""공통 유틸리티 모듈 - 로깅 설정"""

import logging
import sys


def setup_logger(name: str = "webtoon", level: int = logging.INFO) -> logging.Logger:
    """프로젝트 공통 로거를 생성합니다."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    return logger


log = setup_logger()
