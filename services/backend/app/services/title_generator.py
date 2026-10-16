"""
Title Generator Service
Phase 18.6: 세션 제목 자동 생성

LLM을 사용하여 세션 제목을 자동 생성하는 서비스
"""
from typing import Any, List, Dict, Optional


class TitleGeneratorService:
    """세션 제목 자동 생성 서비스

    LLM을 사용하여 대화의 첫 몇 개 메시지를 기반으로
    세션 제목을 자동으로 생성합니다.
    """

    def __init__(self, llm_client: Any = None, db_store: Any = None):
        """
        Args:
            llm_client: LLM 클라이언트 (generate 메서드 필요)
            db_store: DB 저장소 (update_session_title 메서드 필요)
        """
        self.llm_client = llm_client
        self.db_store = db_store

        # 제목 생성용 프롬프트
        self.title_prompt = """다음 대화의 내용을 보고, 이 대화를 가장 잘 설명하는 짧은 제목을 생성해주세요.
제목은 15자 이내로 간결하게 작성해주세요.
제목만 출력하고 다른 설명은 하지 마세요.

대화 내용:
{conversation}

제목:"""

    async def generate_title(
        self,
        messages: List[Dict[str, str]],
        max_messages: int = 3
    ) -> Optional[str]:
        """대화 메시지를 기반으로 제목 생성

        Args:
            messages: 대화 메시지 리스트 [{"role": "...", "content": "..."}]
            max_messages: 제목 생성에 사용할 최대 메시지 수

        Returns:
            생성된 제목 또는 None
        """
        if not self.llm_client or not messages:
            return None

        # 첫 몇 개의 메시지만 사용
        limited_messages = messages[:max_messages]

        # 대화 내용을 문자열로 변환
        conversation = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in limited_messages
        ])

        # LLM에 제목 생성 요청
        prompt = self.title_prompt.format(conversation=conversation)

        try:
            title = await self.llm_client.generate(prompt)
            # 제목 정리 (앞뒤 공백 및 따옴표 제거)
            if title:
                title = title.strip().strip('"\'')
            return title
        except Exception:
            return None

    async def generate_and_save_title(
        self,
        session_id: str,
        messages: List[Dict[str, str]]
    ) -> Optional[str]:
        """제목을 생성하고 DB에 저장

        Args:
            session_id: 세션 ID
            messages: 대화 메시지 리스트

        Returns:
            생성된 제목 또는 None
        """
        title = await self.generate_title(messages)

        if title and self.db_store:
            try:
                await self.db_store.update_session_title(
                    session_id=session_id,
                    title=title
                )
            except Exception:
                pass

        return title

    def should_generate_title(self, message_count: int) -> bool:
        """제목 자동 생성 여부 결정

        세 번째 메시지가 저장될 때 자동으로 제목을 생성합니다.
        한 번만 생성되어야 하므로 정확히 3개일 때만 True를 반환합니다.

        Args:
            message_count: 현재 세션의 메시지 수

        Returns:
            True: 제목 생성 필요, False: 생성 불필요
        """
        return message_count == 3
