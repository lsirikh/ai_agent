"""
EnvWriterService - .env 파일 동기화 서비스

Phase 16: Settings-Environment 동기화 시스템
Settings 페이지에서 설정 변경 시 DB와 .env 파일 동시 업데이트
"""
import os
from pathlib import Path
from typing import Dict, Optional


# Settings 키 → 환경변수 매핑
# None = 런타임 설정 (재시작 불필요, .env 저장 안함)
SETTINGS_ENV_MAP: Dict[str, Dict[str, Optional[str]]] = {
    "llm": {
        "model": "LLM_MODEL",
        "temperature": None,  # 런타임 설정
        "max_tokens": None,   # 런타임 설정
    },
    "stt": {
        "model_size": "STT_MODEL_SIZE",
        "language": None,     # 런타임 설정
    },
    "tts": {
        "engine": "TTS_ENGINE",
        "voice": "TTS_VOICE",
        "speed": None,        # 런타임 설정
    },
}

# UI 표시용 짧은 ID → HuggingFace 전체 경로 매핑
# Downloaded models only (8 models)
MODEL_ID_MAP: Dict[str, str] = {
    # Qwen3.5 (대화·도구·이미지 이해, 권장)
    "qwen3.5-9b": "RedHatAI/Qwen3.5-9B-quantized.w4a16",
    # Qwen 시리즈 (다운로드됨)
    "qwen2.5-3b-instruct": "Qwen/Qwen2.5-3B-Instruct",
    "qwen2.5-7b-instruct-awq": "Qwen/Qwen2.5-7B-Instruct-AWQ",
    "qwen2.5-14b-instruct-awq": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "qwen2.5-72b-instruct-awq": "Qwen/Qwen2.5-72B-Instruct-AWQ",
    # Phi-4 (다운로드됨)
    "phi-4-mini-instruct": "microsoft/Phi-4-mini-instruct",
    # DeepSeek R1 시리즈 (다운로드됨)
    "deepseek-r1-distill-qwen-7b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "deepseek-r1-distill-qwen-14b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
    "deepseek-r1-distill-llama-8b": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
}


def get_model_path(model_id: str) -> str:
    """
    짧은 모델 ID를 전체 HuggingFace 경로로 변환

    Args:
        model_id: 짧은 모델 ID 또는 전체 경로

    Returns:
        전체 HuggingFace 경로 (없으면 원본 반환)
    """
    return MODEL_ID_MAP.get(model_id, model_id)


class EnvWriterService:
    """
    .env 파일 읽기/쓰기 서비스
    Settings 변경 시 .env 파일 동기화
    """

    def __init__(self, env_path: Optional[str] = None):
        """
        EnvWriterService 초기화

        Args:
            env_path: .env 파일 경로. 없으면 ENV_FILE_PATH 환경변수 또는 기본값 사용
        """
        self.env_path = Path(env_path or os.getenv(
            "ENV_FILE_PATH",
            "/app/.env"
        ))
        self._ensure_env_exists()

    def _ensure_env_exists(self):
        """없으면 .env 파일 생성"""
        if not self.env_path.exists():
            # 부모 디렉토리가 없으면 생성
            self.env_path.parent.mkdir(parents=True, exist_ok=True)
            # 빈 파일 생성
            self.env_path.touch()

    def read_all(self) -> Dict[str, str]:
        """
        전체 .env 파일 읽기

        Returns:
            키-값 딕셔너리. 주석과 빈 줄은 무시됨.
        """
        env_vars = {}
        if self.env_path.exists():
            for line in self.env_path.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                # 빈 줄이나 주석은 무시
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
        return env_vars

    def read(self, key: str) -> Optional[str]:
        """
        특정 키의 값 읽기

        Args:
            key: 환경변수 키

        Returns:
            값 또는 None (키가 없는 경우)
        """
        return self.read_all().get(key)

    def write(self, key: str, value: str) -> bool:
        """
        특정 키 업데이트 (없으면 추가)
        주석과 빈 줄은 보존됨.

        Args:
            key: 환경변수 키
            value: 값

        Returns:
            성공 여부
        """
        lines = []
        found = False

        if self.env_path.exists():
            for line in self.env_path.read_text(encoding='utf-8').splitlines():
                stripped = line.strip()
                # 해당 키를 찾아 업데이트
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    line_key = stripped.split('=', 1)[0].strip()
                    if line_key == key:
                        lines.append(f"{key}={value}")
                        found = True
                        continue
                lines.append(line)

        # 새 키인 경우 추가
        if not found:
            lines.append(f"{key}={value}")

        self.env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return True

    def write_many(self, updates: Dict[str, str]) -> bool:
        """
        여러 키 동시 업데이트

        Args:
            updates: 키-값 딕셔너리

        Returns:
            성공 여부
        """
        for key, value in updates.items():
            self.write(key, value)
        return True
