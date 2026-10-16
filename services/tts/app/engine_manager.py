"""
TTS Engine Manager

Phase 10.1.6: 동적 엔진 전환 매니저 구현
"""
from typing import Dict, List, Optional, Union

import numpy as np

from .engines.base import TTSEngine, TTSEngineType
from .engines.melo_engine import MeloTTSEngine
from .engines.kokoro_engine import KokoroTTSEngine
from .engines.edge_tts_engine import EdgeTTSEngine
from .engines.gtts_engine import GTTSEngine


class TTSEngineManager:
    """TTS 엔진 동적 관리자

    특징:
    - Hot-swap: 엔진 즉시 전환 가능
    - Lazy loading: 필요 시에만 엔진 로드
    - 현재 엔진 상태 관리
    """

    def __init__(self, default_engine: Union[TTSEngineType, str] = TTSEngineType.MELO):
        """
        TTSEngineManager 초기화

        Args:
            default_engine: 기본 엔진 타입
        """
        self._engines: Dict[str, TTSEngine] = {}
        self._current_engine_type: TTSEngineType = self._normalize_engine_type(default_engine)

        # 기본 엔진 로드
        self._ensure_engine_loaded(self._current_engine_type)

    def _normalize_engine_type(self, engine: Union[TTSEngineType, str]) -> Optional[TTSEngineType]:
        """엔진 타입 정규화

        Args:
            engine: 엔진 타입 또는 문자열

        Returns:
            TTSEngineType 또는 None (잘못된 타입인 경우)
        """
        if isinstance(engine, TTSEngineType):
            return engine

        try:
            return TTSEngineType(engine)
        except ValueError:
            return None

    def _create_engine(self, engine_type: TTSEngineType) -> TTSEngine:
        """엔진 인스턴스 생성

        Args:
            engine_type: 엔진 타입

        Returns:
            TTSEngine 인스턴스
        """
        if engine_type == TTSEngineType.MELO:
            return MeloTTSEngine()
        elif engine_type == TTSEngineType.KOKORO:
            return KokoroTTSEngine()
        elif engine_type == TTSEngineType.EDGE_TTS:
            return EdgeTTSEngine()
        elif engine_type == TTSEngineType.GTTS:
            return GTTSEngine()
        else:
            raise ValueError(f"Unknown engine type: {engine_type}")

    def _ensure_engine_loaded(self, engine_type: TTSEngineType) -> None:
        """엔진이 로드되어 있는지 확인하고, 없으면 로드

        Args:
            engine_type: 엔진 타입
        """
        if engine_type.value not in self._engines:
            self._engines[engine_type.value] = self._create_engine(engine_type)

    def get_engine(self, engine: Union[TTSEngineType, str]) -> Optional[TTSEngine]:
        """특정 엔진 조회

        Args:
            engine: 엔진 타입 또는 문자열

        Returns:
            TTSEngine 인스턴스 또는 None
        """
        engine_type = self._normalize_engine_type(engine)
        if engine_type is None:
            return None
        self._ensure_engine_loaded(engine_type)
        return self._engines.get(engine_type.value)

    def get_current_engine(self) -> TTSEngine:
        """현재 엔진 조회

        Returns:
            현재 TTSEngine 인스턴스
        """
        return self._engines[self._current_engine_type.value]

    def switch_engine(self, engine: Union[TTSEngineType, str]) -> bool:
        """엔진 전환 (hot-swap)

        Args:
            engine: 새 엔진 타입 또는 문자열

        Returns:
            True: 전환 성공, False: 전환 실패
        """
        try:
            engine_type = self._normalize_engine_type(engine)

            # 유효한 엔진 타입인지 확인
            if engine_type is None:
                return False

            self._ensure_engine_loaded(engine_type)
            self._current_engine_type = engine_type

            print(f"[TTS] Engine switched to: {engine_type.value}")
            return True

        except Exception as e:
            print(f"[TTS] Engine switch failed: {e}")
            return False

    def list_engines(self) -> List[dict]:
        """사용 가능한 엔진 목록 조회

        Returns:
            엔진 정보 리스트
        """
        engines_info = []

        for engine_type in TTSEngineType:
            self._ensure_engine_loaded(engine_type)
            engine = self._engines[engine_type.value]

            info = engine.get_info()
            info["is_current"] = (engine_type == self._current_engine_type)
            engines_info.append(info)

        return engines_info

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0
    ) -> np.ndarray:
        """현재 엔진으로 텍스트 합성

        Args:
            text: 합성할 텍스트
            voice: 음성 ID (None이면 기본)
            speed: 발화 속도

        Returns:
            np.ndarray: float32 오디오 데이터
        """
        engine = self.get_current_engine()
        return engine.synthesize(text, voice=voice, speed=speed)

    def get_current_engine_type(self) -> TTSEngineType:
        """현재 엔진 타입 조회

        Returns:
            현재 TTSEngineType
        """
        return self._current_engine_type

    def get_current_engine_name(self) -> str:
        """현재 엔진 이름(문자열) 조회

        Returns:
            현재 엔진 이름 문자열
        """
        return self._current_engine_type.value

    def get_available_engines(self) -> List[dict]:
        """사용 가능한 엔진 목록 조회 (list_engines 별칭)

        Returns:
            엔진 정보 리스트
        """
        return self.list_engines()
