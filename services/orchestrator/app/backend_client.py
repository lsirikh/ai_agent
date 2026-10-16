"""
Backend Client
Phase 19.1: Orchestrator 상태 보고 클라이언트
Phase 19.3: 세션 자동 생성/동기화

Orchestrator에서 Backend로 상태를 보고하고 세션을 관리하는 HTTP 클라이언트
"""
import os
from typing import Optional

import httpx


class BackendClient:
    """Backend API 클라이언트"""

    # 음성 턴을 막지 않도록 짧게 기다린다
    TIMEOUT_SECONDS = 5.0

    def __init__(self, base_url: Optional[str] = None):
        """
        BackendClient 초기화

        Args:
            base_url: Backend 서버 URL (기본값: 환경변수 BACKEND_URL 또는 http://backend:11000)
        """
        self.base_url = base_url or os.getenv("BACKEND_URL", "http://backend:11000")
        self.current_session_id: Optional[str] = None

    async def report_state(
        self,
        state: str,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Orchestrator 상태를 Backend에 보고

        Args:
            state: 현재 상태 (LISTENING, STT_PROCESSING, LLM_PROCESSING, TTS_PROCESSING, ERROR 등)
            session_id: 세션 ID (선택)
            metadata: 추가 메타데이터 (선택)

        Returns:
            Backend 응답 결과
        """
        url = f"{self.base_url}/api/orchestrator/state"

        payload = {
            "state": state
        }

        if session_id:
            payload["session_id"] = session_id

        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def create_session(
        self,
        source: str = "orchestrator",
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Backend에 새 세션 생성 요청

        Args:
            source: 세션 소스 (sessions.source 제약: web, orchestrator, api)
            metadata: 추가 메타데이터 (선택)

        Returns:
            생성된 세션 정보 (session_id 포함)
        """
        url = f"{self.base_url}/api/sessions/pipeline"

        payload = {
            "source": source,
            "type": "voice"
        }

        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            # 현재 세션 ID 저장
            if "session_id" in result:
                self.current_session_id = result["session_id"]

            return result

    async def get_active_session(self) -> str:
        """음성·채팅이 함께 쓰는 활성 세션 ID (없으면 백엔드가 만든다)."""
        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            response = await client.get(f"{self.base_url}/api/sessions/active")
            response.raise_for_status()
            self.current_session_id = response.json()["session_id"]
            return self.current_session_id

    async def get_context(self, session_id: str) -> dict:
        """
        프롬프트용 세션 컨텍스트:
        {"summary": str|None, "messages": [{"role", "content"}, ...]}
        """
        url = f"{self.base_url}/api/sessions/{session_id}/context"
        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def save_message(
        self,
        role: str,
        content: str,
        source: str = "voice",
        audio_url: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        메시지를 Backend에 저장

        Args:
            role: 메시지 역할 (user, assistant)
            content: 메시지 내용
            source: 메시지 소스 (voice, web 등)
            audio_url: 오디오 파일 URL (선택)
            metadata: 추가 메타데이터 (선택)

        Returns:
            저장된 메시지 정보 (message_id 포함)
        """
        url = f"{self.base_url}/api/sessions/pipeline/messages"

        payload = {
            "session_id": self.current_session_id,
            "role": role,
            "content": content,
            "source": source
        }

        if audio_url:
            payload["audio_url"] = audio_url

        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
