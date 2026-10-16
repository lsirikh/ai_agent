"""
Test: Title Generator Service
Phase 18.6: 세션 제목 자동 생성

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_title_generator_service_exists():
    """TitleGeneratorService 클래스가 존재하는지 확인"""
    from app.services.title_generator import TitleGeneratorService
    assert TitleGeneratorService is not None


def test_generate_title_uses_llm():
    """제목 생성 시 LLM을 사용하는지 확인"""
    from app.services.title_generator import TitleGeneratorService

    # TitleGeneratorService가 llm_client를 받는지 확인
    import inspect
    sig = inspect.signature(TitleGeneratorService.__init__)
    params = list(sig.parameters.keys())
    assert "llm_client" in params, "TitleGeneratorService는 llm_client 파라미터를 받아야 합니다"


@pytest.mark.asyncio
async def test_generate_title_uses_first_messages():
    """제목 생성 시 첫 몇 개의 메시지를 사용하는지 확인"""
    from app.services.title_generator import TitleGeneratorService

    # Mock LLM client
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = "테스트 대화 제목"

    service = TitleGeneratorService(llm_client=mock_llm)

    messages = [
        {"role": "user", "content": "안녕하세요"},
        {"role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?"},
        {"role": "user", "content": "오늘 날씨 어때요?"}
    ]

    title = await service.generate_title(messages=messages)

    # LLM이 호출되었는지 확인
    assert mock_llm.generate.called, "LLM generate 메서드가 호출되어야 합니다"
    assert title is not None


@pytest.mark.asyncio
async def test_generate_title_updates_db():
    """생성된 제목이 DB에 업데이트되는지 확인"""
    from app.services.title_generator import TitleGeneratorService

    # Mock LLM client
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = "새로운 대화 제목"

    # Mock DB store
    mock_db = AsyncMock()

    service = TitleGeneratorService(llm_client=mock_llm, db_store=mock_db)

    messages = [
        {"role": "user", "content": "안녕하세요"},
        {"role": "assistant", "content": "안녕하세요!"},
        {"role": "user", "content": "질문이 있어요"}
    ]

    await service.generate_and_save_title(
        session_id="test-session-123",
        messages=messages
    )

    # DB 업데이트가 호출되었는지 확인
    assert mock_db.update_session_title.called, "DB update_session_title이 호출되어야 합니다"


@pytest.mark.asyncio
async def test_auto_title_at_third_message():
    """세 번째 메시지에서 자동으로 제목이 생성되는지 확인"""
    from app.services.title_generator import TitleGeneratorService

    # TitleGeneratorService에 should_generate_title 메서드가 있는지 확인
    service = TitleGeneratorService()

    # 3개 미만의 메시지: 제목 생성 안함
    assert service.should_generate_title(message_count=1) is False
    assert service.should_generate_title(message_count=2) is False

    # 3개 메시지: 제목 생성
    assert service.should_generate_title(message_count=3) is True

    # 3개 초과: 이미 생성되었을 것이므로 생성 안함
    assert service.should_generate_title(message_count=4) is False
    assert service.should_generate_title(message_count=10) is False
