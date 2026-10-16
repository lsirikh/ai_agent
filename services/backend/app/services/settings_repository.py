"""
Backend Services - Settings Repository

Phase 12.1: Settings DB 영속성
"""
import json
import os
from typing import Any, Dict, Optional

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:
    psycopg2 = None


# 기본 설정값
DEFAULT_SETTINGS = {
    "llm": {
        "model": "qwen2.5-7b-instruct-awq",
        "temperature": 0.7,
        "max_tokens": 1024,
        "system_prompt": "당신은 EdgeVoice AI 어시스턴트입니다. 친절하고 정확하게 한국어로만 제공해주세요."
    },
    "tts": {
        "engine": "melo",
        "voice": "af_heart",
        "speed": 1.0
    },
    "stt": {
        "model": "small",
        "language": "ko",
        "model_size": "large-v3"
    },
    "audio": {
        "sample_rate": 16000,
        "vad_threshold": 0.5,
        "silence_duration": 0.5
    }
}


class SettingsRepository:
    """
    Settings DB 영속성을 위한 리포지토리 클래스.
    PostgreSQL의 settings 테이블을 사용하여 설정을 저장/로드.
    """

    def __init__(self, database_url: Optional[str] = None):
        """
        SettingsRepository 초기화.

        Args:
            database_url: PostgreSQL 연결 URL
        """
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql://edgevoice:edgevoice@localhost:5432/edgevoice"
        )

    def _get_connection(self):
        """데이터베이스 연결 반환"""
        if psycopg2 is None:
            raise ImportError("psycopg2 is not installed")
        return psycopg2.connect(self.database_url)

    def save(self, settings_type: str, settings_data: Dict[str, Any]) -> bool:
        """
        설정을 DB에 저장 (UPSERT).

        Args:
            settings_type: 설정 타입 (llm, tts, stt, audio)
            settings_data: 저장할 설정 데이터

        Returns:
            저장 성공 여부
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # UPSERT 쿼리 (INSERT ... ON CONFLICT UPDATE)
                    query = """
                        INSERT INTO settings (key, value, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (key)
                        DO UPDATE SET value = %s, updated_at = NOW()
                    """
                    json_value = json.dumps(settings_data)
                    cursor.execute(query, (settings_type, json_value, json_value))
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def load(self, settings_type: str) -> Dict[str, Any]:
        """
        DB에서 설정 로드.

        Args:
            settings_type: 설정 타입 (llm, tts, stt, audio)

        Returns:
            설정 데이터 (없으면 기본값)
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    query = "SELECT value FROM settings WHERE key = %s"
                    cursor.execute(query, (settings_type,))
                    result = cursor.fetchone()

                    if result and result[0]:
                        # JSON 문자열 또는 dict 처리
                        value = result[0]
                        if isinstance(value, str):
                            return json.loads(value)
                        return value

        except Exception as e:
            print(f"Error loading settings: {e}")

        # DB에 없거나 오류 시 기본값 반환
        return DEFAULT_SETTINGS.get(settings_type, {})

    def load_all(self) -> Dict[str, Dict[str, Any]]:
        """
        모든 설정 로드.

        Returns:
            전체 설정 딕셔너리
        """
        all_settings = {}
        for settings_type in ["llm", "tts", "stt", "audio"]:
            all_settings[settings_type] = self.load(settings_type)
        return all_settings

    def delete(self, settings_type: str) -> bool:
        """
        설정 삭제.

        Args:
            settings_type: 설정 타입

        Returns:
            삭제 성공 여부
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    query = "DELETE FROM settings WHERE key = %s"
                    cursor.execute(query, (settings_type,))
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error deleting settings: {e}")
            return False


# 싱글톤 인스턴스
_settings_repository: Optional[SettingsRepository] = None


def get_settings_repository() -> SettingsRepository:
    """SettingsRepository 싱글톤 인스턴스 반환"""
    global _settings_repository
    if _settings_repository is None:
        _settings_repository = SettingsRepository()
    return _settings_repository


def reset_settings_repository():
    """SettingsRepository 리셋 (테스트용)"""
    global _settings_repository
    _settings_repository = None
