"""
Settings-Environment 동기화 서비스

Phase 16.3: Settings 변경 시 .env 파일 동기화
Settings 페이지에서 apply 호출 시 DB와 .env 파일 동시 업데이트
"""
import os
from typing import Dict, Any, Optional

from .env_writer import (
    EnvWriterService,
    SETTINGS_ENV_MAP,
    get_model_path,
)


def sync_settings_to_env(
    settings_data: Dict[str, Any],
    env_path: Optional[str] = None
) -> bool:
    """
    Settings 데이터를 .env 파일에 동기화

    Args:
        settings_data: 설정 데이터 (예: {"llm": {"model": "qwen2.5-7b"}, ...})
        env_path: .env 파일 경로 (테스트용)

    Returns:
        성공 여부
    """
    if not settings_data:
        # 빈 설정이면 파일만 생성하고 종료
        writer = EnvWriterService(env_path=env_path)
        return True

    writer = EnvWriterService(env_path=env_path)
    updates: Dict[str, str] = {}

    for category, settings in settings_data.items():
        if category not in SETTINGS_ENV_MAP:
            continue

        category_map = SETTINGS_ENV_MAP[category]

        for key, value in settings.items():
            if key not in category_map:
                continue

            env_key = category_map[key]

            # None = 런타임 설정, .env에 저장하지 않음
            if env_key is None:
                continue

            # 모델 ID 변환 (짧은 ID → 전체 HuggingFace 경로)
            if key == "model" and category == "llm":
                value = get_model_path(value)

            updates[env_key] = str(value)

    if updates:
        writer.write_many(updates)

    return True
